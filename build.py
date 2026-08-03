#!/usr/bin/env python3
"""JeffOps.com static site build.

Renders every markdown post to a real HTML page at build time, so that each
article has its own URL, its own metadata, and its own content in the response
body — visible to search engines, AI crawlers, and link preview cards, none of
which run JavaScript.

The single-page app is left intact and keeps working; this adds the crawlable
layer underneath it.

Usage:  python build.py            → output in _site/
        python build.py --out dir  → output elsewhere
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import quote

try:
    from zoneinfo import ZoneInfo
except ImportError:      # pragma: no cover
    ZoneInfo = None

import markdown

from generate_blog_index import (ROOT, collect_posts, estimate_readtime, find_markdown_file,
                                 in_site_tz,
                                 parse_excerpt, parse_frontmatter, parse_title, slugify,
                                 strip_frontmatter, strip_leading_h1, unpublished_posts,
                                 utc_now, write_index_files)

# ── Site configuration ────────────────────────────────────────────────
SITE = {
    'base_url': 'https://jeffops.com',
    'title': 'JeffOps',
    'tagline': 'Jeff. Tech. Dev. Ops.',
    'description': 'Practical AI-tomation, platform engineering and enterprise '
                   'ops from Jeff Wouters. Written from inside a 25,000-user '
                   'environment, not from a vendor deck.',
    'author': 'Jeff Wouters',
    'email': 'jeff@jeffops.com',
    'language': 'en',
    'og_image': '/og-card.png',
}

# Files and folders copied verbatim into the output.
STATIC_ASSETS = ['index.html', 'css', 'js', 'logos', 'speaking_topics.json']

# Images in the project root are copied by pattern rather than by name. The list
# above used to carry 'JeffOps_Speaking.jpg' literally, so a second photo added
# next to it was simply never copied, and the page referencing it would have
# shown a broken image with nothing anywhere reporting a problem.
ROOT_ASSET_PATTERNS = ('*.jpg', '*.jpeg', '*.png', '*.webp', '*.svg', '*.gif')

MD_EXTENSIONS = ['fenced_code', 'tables', 'attr_list', 'sane_lists', 'toc', 'footnotes']
MD_CONFIG = {'toc': {'permalink': False, 'toc_depth': '2-3'}}



# ── Publication ───────────────────────────────────────────────────────
BLOG_INDEX_FILES = ('index.json', 'index.js', 'topics.json', 'series.json', 'speaking.js')

# Marks a page rendered by a preview build. verify_build refuses to ship a build
# containing it, so a preview can never be mistaken for the real thing.
PREVIEW_MARK = 'data-preview-build="1"'

PREVIEW_BANNER = (
    '<div ' + PREVIEW_MARK + ' style="border:1px solid #d2593c;border-left-width:4px;'
    'padding:0.9rem 1.1rem;margin:0 0 2rem;font-size:0.9rem;line-height:1.6;">'
    '<strong>Preview.</strong> This post is scheduled and is not on the live site. '
    'Publication date: {when}.</div>'
)


def copy_blog(out: Path, posts: list[dict]) -> None:
    """Copy the browser index files, and the folder of each published post only.

    The build used to copy blog/ wholesale, which published every post.md at its
    own folder path. A scheduled post would then have been readable in full,
    correctly formatted, by anyone who guessed the URL, while the site showed no
    trace of it. Copying per post is what makes the schedule mean anything.
    """
    src, dst = ROOT / 'blog', out / 'blog'
    dst.mkdir(parents=True, exist_ok=True)
    for name in BLOG_INDEX_FILES:
        if (src / name).exists():
            shutil.copy2(src / name, dst / name)
    for post in posts:
        folder = ROOT / post['folder']
        if folder.is_dir():
            shutil.copytree(folder, out / post['folder'], dirs_exist_ok=True)


def _local(post: dict) -> str:
    """The publication moment as the author wrote it, with the UTC in brackets."""
    from generate_blog_index import SITE_TZ_NAME
    when = datetime.fromisoformat(post['published_at'])
    local = when.astimezone(ZoneInfo(SITE_TZ_NAME)) if ZoneInfo else when
    return (f'{local.strftime("%a %d %b %Y, %H:%M")} {local.tzname()} '
            f'({when.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M")} UTC)')


def report_schedule(pending: list[dict]) -> None:
    if not pending:
        return
    drafts = [p for p in pending if p['is_draft']]
    scheduled = sorted((p for p in pending if p['is_scheduled'] and not p['is_draft']),
                       key=lambda p: p['published_at'])
    for post in drafts:
        print(f'  · draft, never published: {post["title"][:58]}')
    for post in scheduled:
        print(f'  · scheduled for {_local(post)}: {post["title"][:46]}')
    if scheduled:
        print(f'  Next post appears at {_local(scheduled[0])}, on the first build at '
              f'or after that moment.')



# ── Redirects ─────────────────────────────────────────────────────────
#
# GitHub Pages serves static files and cannot issue a 3xx, so a moved URL needs
# a page that moves the reader itself. All three mechanisms below are here on
# purpose: the canonical link tells a crawler where the content now lives, the
# meta refresh is what Google reads as a redirect and passes signals through,
# and the script handles the reader who arrives with JavaScript on. The visible
# link is for everyone else.
#
# These exist because jeffops.com served a Hugo site for years. Every URL it
# published and this site does not needs somewhere to land, or the migration
# quietly breaks every link anyone ever shared.

REDIRECT_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Moved — {site_title}</title>
<link rel="canonical" href="{absolute}">
<meta http-equiv="refresh" content="0; url={target}">
<meta name="robots" content="noindex, follow">
<script>window.location.replace("{target}");</script>
</head>
<body style="font-family:system-ui,sans-serif;background:#0a0c0f;color:#e8edf2;padding:3rem">
<p>This page has moved to <a style="color:#00d9ff" href="{target}">{target}</a>.</p>
</body>
</html>
"""


def load_redirects() -> dict:
    path = ROOT / 'redirects.json'
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding='utf-8'))


def write_redirects(out: Path, redirects: dict, taken: set) -> list[str]:
    written = []
    for source, target in sorted(redirects.items()):
        rel = source.strip('/')
        if not rel:
            print(f'  ! Refusing to redirect the site root')
            continue
        # A redirect that shadows a real page would silently replace it, and the
        # page would look fine right up until someone opened it.
        if '/' + rel + '/' in taken:
            print(f'  ! Refusing to write a redirect at {source}: a real page lives there')
            continue
        page_dir = out / rel
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / 'index.html').write_text(REDIRECT_TEMPLATE.format(
            site_title=SITE['title'],
            target=target,
            absolute=SITE['base_url'] + (target if target.startswith('/') else '/' + target),
        ), encoding='utf-8')
        written.append(source)
    return written



# ── Home page statistics ──────────────────────────────────────────────
#
# Every number in the hero used to be typed into the HTML by hand: "128+
# Articles" against seven real posts, "12K Subscribers" with no source
# anywhere, "40+ Talks" against a file holding five. A number nobody can trace
# is indistinguishable from one that is made up, and on a personal site it is
# the author who carries that.
#
# So: anything countable is counted here, at build time, and cannot drift.
# Anything not countable lives in stats.json with a source and a date it was
# last checked. A stat with no value is left off the page rather than guessed,
# and one whose check has gone stale fails the build.

STATS_MAX_AGE_DAYS = 183


def load_stats() -> dict:
    path = ROOT / 'stats.json'
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding='utf-8')).get('stats', {})


def derived_stats(posts: list[dict], talks: list[dict], editions: list[dict]) -> list[tuple]:
    """The numbers the repository can prove, as (value, label) pairs."""
    years = {p['iso'][:4] for p in posts if p.get('iso')}
    span = (max(int(y) for y in years) - min(int(y) for y in years) + 1) if years else 0
    out = [(str(len(posts)), 'Articles')]
    if talks:
        out.append((str(len(talks)), 'Talks'))
    if editions:
        out.append((str(len(editions)), 'Newsletter editions'))
    if span > 1:
        out.append((f'{span}', 'Years writing'))
    return out


def build_stat_cells(posts, talks, editions, fail=print) -> tuple[str, int]:
    """Return the rendered cells and how many of them came from stats.json.

    The count is of figures actually accepted, not of figures present in the
    file: a rejected one falls back to the derived number, and a build log that
    said otherwise would be describing a page that was not built.
    """
    cells = derived_stats(posts, talks, editions)
    declared = 0

    today = datetime.now(timezone.utc).date()
    for key, meta in load_stats().items():
        value = meta.get('value')
        if value in (None, ''):
            continue                       # not known yet, so not claimed
        checked = meta.get('verified')
        if not checked:
            fail(f'stats.json: "{key}" has a value but no verified date')
            continue
        age = (today - datetime.fromisoformat(str(checked)).date()).days
        if age > STATS_MAX_AGE_DAYS:
            fail(f'stats.json: "{key}" was last verified {age} days ago. '
                 f'Re-check it or remove the value.')
            continue
        # A stats.json entry whose label matches a derived one replaces it in
        # place rather than appending. The derived Talks figure counts the talks
        # listed in speaking_talks.json, which is a selection, not a career
        # total -- it read "5 Talks" for someone who has given far more. Where a
        # declared figure and a derived one describe the same thing, the
        # declared one wins, and the cell keeps its position so the bar does not
        # reshuffle. Delete the value and the derived count comes back.
        label = meta.get('label', key)
        declared += 1
        for i, (_, existing) in enumerate(cells):
            if existing.casefold() == label.casefold():
                cells[i] = (str(value), label)
                break
        else:
            cells.append((str(value), label))

    markup = ''.join(
        f'<div class="stat-cell"><span class="stat-val">{html.escape(v)}</span>'
        f'<span class="stat-lbl">{html.escape(l)}</span></div>'
        for v, l in cells[:4]
    )
    return markup, declared


def inject_stats(index_html: str, cells: str) -> str:
    """Replace the hero stat cells with the generated ones."""
    m = re.search(r'<div class="stats-bar">.*?\n\s*</div>', index_html, re.DOTALL)
    if not m:
        # Silence here would mean shipping whatever numbers happen to be typed
        # into the HTML, which is the exact failure this replaced.
        raise SystemExit('Could not find <div class="stats-bar"> in index.html. '
                         'The home page statistics could not be generated, and '
                         'hand-written ones must not ship.')
    return (index_html[:m.start()] + '<div class="stats-bar">' + cells + '</div>'
            + index_html[m.end():])


def normalise_talks(talks: list[dict]) -> list[dict]:
    """Derive each talk's status from its date.

    Status used to be stored, and two talks sat on the live site marked
    Upcoming for conferences that had happened 502 and 557 days earlier. A
    stored status is a second copy of a fact the date already carries, and the
    copy is the one that rots. With the daily build, this flips on the day.
    """
    today = datetime.now(timezone.utc).date()
    out = []
    for talk in talks:
        item = dict(talk)
        try:
            upcoming = datetime.fromisoformat(str(talk.get('date'))).date() >= today
        except (TypeError, ValueError):
            upcoming = False
        item['status'] = 'Upcoming' if upcoming else 'Past'
        item['statusLabel'] = item['status']
        out.append(item)
    return sorted(out, key=lambda t: str(t.get('date', '')), reverse=True)



# ── Home page metadata ────────────────────────────────────────────────
#
# The home page is hand-written, and it was missing the three things that
# matter most on the one URL most likely to rank for the author's own name: a
# meta description, a canonical, and any structured data at all. It had Open
# Graph and Twitter cards, which serve social previews and do nothing for
# search. These are injected at build time rather than typed in, so they cannot
# drift from the site configuration or from the posts that actually exist.

def home_json_ld(posts: list[dict]) -> str:
    person = {
        '@type': 'Person',
        '@id': SITE['base_url'] + '/#person',
        'name': SITE['author'],
        'url': SITE['base_url'] + '/',
        'email': f"mailto:{SITE['email']}",
        'jobTitle': 'Platform and enterprise IT engineer',
        'description': SITE['description'],
        # Confirmed by Jeff, and the same four the About sidebar links to.
        # sameAs is how a search engine ties these profiles to one person, so a
        # wrong entry here is worse than a missing one.
        'sameAs': ['https://github.com/jeffwouters',
                   'https://www.linkedin.com/in/jeffwouters/',
                   'https://x.com/jeffwouters',
                   'https://www.youtube.com/@JeffOps'],
    }
    website = {
        '@type': 'WebSite',
        '@id': SITE['base_url'] + '/#website',
        'url': SITE['base_url'] + '/',
        'name': SITE['title'],
        'description': SITE['description'],
        'inLanguage': SITE['language'],
        'publisher': {'@id': SITE['base_url'] + '/#person'},
    }
    blog = {
        '@type': 'Blog',
        '@id': SITE['base_url'] + '/posts/',
        'url': SITE['base_url'] + '/posts/',
        'name': f"{SITE['title']} Blog",
        'author': {'@id': SITE['base_url'] + '/#person'},
        'blogPost': [{'@type': 'BlogPosting',
                      'headline': p['title'],
                      'url': canonical_for(p),
                      'datePublished': p.get('iso', '')} for p in posts[:10]],
    }
    return json.dumps({'@context': 'https://schema.org',
                       '@graph': [person, website, blog]},
                      ensure_ascii=False, indent=2)


def load_events() -> list[str]:
    path = ROOT / 'events.json'
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding='utf-8')).get('events', [])


def inject_events(index_html: str) -> str:
    """Render the "As seen at" strip from events.json.

    The strip previously listed KubeCon EU, LeadDev London, HashiConf,
    DockerCon, Platform Eng Con, GOTO Copenhagen and GitHub Universe, none of
    which Jeff had spoken at. It is the most quotable claim on the site and the
    easiest for anyone in the audience to check, so it gets a source file and a
    build-time render like everything else that asserts a fact.
    """
    events = load_events()
    if not events:
        return index_html
    items = ''.join(
        f'<span class="logo-item"><span class="logo-dot"></span>{html.escape(e)}</span>'
        for e in events)
    m = re.search(r'<div class="logos-track">.*?\n?\s*</div>', index_html, re.DOTALL)
    if not m:
        raise SystemExit('Could not find <div class="logos-track"> in index.html.')
    return (index_html[:m.start()] + '<div class="logos-track">' + items + '</div>'
            + index_html[m.end():])


def inject_counts(index_html: str, posts: list[dict], talks: list[dict]) -> str:
    """Fill the {posts} and {talks} placeholders in the hero orbit tooltips.

    These are the same claims as the statistics bar, one layer down and easy to
    miss: they read "128+ articles" and "40+ conference talks, KubeCon, LeadDev,
    HashiConf" while the site had seven posts, five talks and no LeadDev
    appearance anywhere. Anything with a number in it gets counted.
    """
    return (index_html
            .replace('{posts}', str(len(posts)))
            .replace('{talks}', str(len(talks))))


def inject_home_meta(index_html: str, posts: list[dict]) -> str:
    if 'rel="canonical"' in index_html:
        return index_html
    # One description, from SITE. This used to read the literal out of
    # index.html and defer to it, which meant the site had two descriptions of
    # itself and the stale one was the copy that reached a link preview.
    description = html.escape(SITE['description'])
    index_html = index_html.replace('{description}', description)
    head = (f'<link rel="canonical" href="{SITE["base_url"]}/">\n'
            f'<meta name="description" content="{description}">\n'
            f'<script type="application/ld+json">\n{home_json_ld(posts)}\n</script>\n')
    return index_html.replace('<meta property="og:type"', head + '<meta property="og:type"', 1)


# ── Shell extraction ──────────────────────────────────────────────────
def _absolutise(fragment: str) -> str:
    """Make a fragment lifted from index.html safe to use on a nested page.

    index.html sits at the root, so its links are relative ('css/styles.css')
    and its nav targets are bare hashes ('#blog'). Dropped onto a page at
    /posts/2023/slug/ both break: the first 404s, the second just changes that
    page's own hash. Both become root-absolute.
    """
    fragment = re.sub(r'(href|src)="(?!https?://|//|/|#|mailto:|data:)', r'\1="/', fragment)
    fragment = re.sub(r'href="#(?!")', 'href="/#', fragment)
    return fragment


def extract_shell(index_html: str) -> tuple[str, str]:
    """Pull the nav and footer out of index.html so the design lives in one place."""
    nav = re.search(r'<nav>.*?</nav>', index_html, re.DOTALL)
    footer = re.search(r'<footer>.*?</footer>', index_html, re.DOTALL)
    if not nav or not footer:
        raise SystemExit('Could not locate <nav> or <footer> in index.html — '
                         'the post template needs both.')
    # index.html ships with Home pre-selected. On a post page that is wrong —
    # the reader is under Content › Blog, so move the highlight there.
    nav_html = _absolutise(nav.group(0)).replace(' class="active"', '')
    nav_html = nav_html.replace('id="nav-content"', 'id="nav-content" class="active"')
    nav_html = nav_html.replace('id="nav-blog"', 'id="nav-blog" class="active"')
    return nav_html, _absolutise(footer.group(0))


# ── Rendering ─────────────────────────────────────────────────────────
def render_markdown(text: str) -> tuple[str, list[dict]]:
    md = markdown.Markdown(extensions=MD_EXTENSIONS, extension_configs=MD_CONFIG)
    body = md.convert(text)
    toc = []

    def walk(tokens):
        for token in tokens:
            if token['level'] in (2, 3):
                toc.append({'id': token['id'], 'name': token['name'], 'level': token['level']})
            walk(token.get('children', []))

    walk(getattr(md, 'toc_tokens', []))
    return wrap_figures(body), toc


def wrap_figures(html: str) -> str:
    """Put each inline SVG in its own scroll container.

    An SVG scaled to a phone-width column shrinks its labels to about four
    pixels, which is a diagram that technically fits and cannot be read. The
    wrapper lets the figure keep a legible minimum width and scroll sideways on
    its own, instead of scaling to nothing or dragging the whole page into
    horizontal scroll. Feed readers that ignore the class simply see the SVG in
    a div, which is what they saw before.
    """
    return re.sub(r'(<svg\b.*?</svg>)',
                  r'<div class="figure-scroll">\1</div>',
                  html, flags=re.DOTALL)


def canonical_for(post: dict) -> str:
    return post.get('canonical') or SITE['base_url'] + post['url']


def meta_description(post: dict, limit: int = 158) -> str:
    """A description that reads as a finished sentence.

    Search results and preview cards cut around 155–160 characters. Truncating
    to the character limit alone leaves a word sliced in half, which looks
    broken everywhere it appears, so this backs up to a word boundary.
    """
    text = re.sub(r'\s+', ' ', post.get('description') or post.get('excerpt') or '').strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(' ', 1)[0].rstrip(' ,;:—-')
    return cut + '…'


def json_ld(post: dict) -> str:
    data = {
        '@context': 'https://schema.org',
        '@type': 'BlogPosting',
        'headline': post['title'],
        'description': post['description'],
        'author': {'@type': 'Person', 'name': SITE['author'], 'url': SITE['base_url'] + '/#about'},
        'publisher': {'@type': 'Person', 'name': SITE['author']},
        'mainEntityOfPage': {'@type': 'WebPage', '@id': canonical_for(post)},
        'url': canonical_for(post),
        'inLanguage': SITE['language'],
    }
    if post.get('iso'):
        data['datePublished'] = post['iso']
        data['dateModified'] = post['iso']
    if post.get('tags'):
        data['keywords'] = ', '.join(post['tags'])
    # Google reads this for article rich results, and it is a separate field
    # from og:image. Setting one and not the other is the usual half-done job.
    if post.get('cover_url'):
        data['image'] = SITE['base_url'] + post['cover_url']
    return json.dumps(data, ensure_ascii=False, indent=2)


def toc_html(toc: list[dict]) -> str:
    if not toc:
        return ''
    parts = []
    for i, item in enumerate(toc):
        cls = ' class="h3"' if item['level'] == 3 else ''
        parts.append(
            f'<a href="#{item["id"]}" data-idx="{i}" data-target="{item["id"]}"{cls}>'
            f'{html.escape(item["name"])}<span class="toc-progress-dot" id="tdot-{i}"></span></a>'
        )
    return '\n'.join(parts)


def related_html(post: dict, by_folder: dict) -> str:
    cards = []
    for folder in post.get('related', []):
        rel = by_folder.get(folder)
        if not rel:
            continue
        cards.append(
            f'<a class="related-card" href="{rel["url"]}">'
            f'<div class="related-card-type">// Blog Post</div>'
            f'<div class="related-card-title">{html.escape(rel["title"])}</div>'
            f'<div class="related-card-meta">{rel["date"]} · {rel["readtime"]}</div></a>'
        )
    if not cards:
        return ''
    return ('<div class="related-posts"><div class="related-title">// You might also like</div>'
            '<div class="related-grid">' + ''.join(cards) + '</div></div>')


POST_TEMPLATE = """<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — {site_title}</title>
<meta name="description" content="{description}">
<meta name="author" content="{author}">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="article">
<meta property="og:url" content="{canonical}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta property="og:image" content="{og_image_url}">
<meta property="og:site_name" content="{site_title}">
<meta property="article:author" content="{author}">
{article_meta}
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{description}">
<meta name="twitter:image" content="{og_image_url}">
<link rel="alternate" type="application/rss+xml" title="{site_title} Blog" href="{base_url}/rss.xml">
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32x32.png">
<link rel="icon" type="image/png" sizes="16x16" href="/favicon-16x16.png">
<link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png">
<link rel="mask-icon" href="/safari-pinned-tab.svg" color="#00d9ff">
<link rel="manifest" href="/site.webmanifest">
<meta name="msapplication-TileColor" content="#0a0c0f">
<meta name="theme-color" content="#0a0c0f">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css">
<link rel="stylesheet" href="/css/styles.css">
<script type="application/ld+json">
{jsonld}
</script>
</head>
<body class="static-post">
<div id="read-progress"></div>
{nav}
<div class="site-content">
<div id="page-post" class="page active">
  <div class="post-page-wrap">
    <div style="padding-top:2rem;"><a class="back-btn" href="{back_url}">← {back_label}</a></div>
    <div class="post-page-layout">
      <aside class="post-toc-aside">
        <div class="toc-label">Contents</div>
        <div id="toc-links">{toc}</div>
      </aside>
      <article>
        <div class="post-header">
          <div class="post-header-type">// {kicker}</div>
          <h1 id="post-title">{title}</h1>
          <div class="post-header-meta"><span id="post-date">{date}</span><span id="post-readtime">{readtime}</span><span>{author}</span></div>
          {tags}
        </div>
{cover}
{origin}
        <div class="post-content" id="post-content">
{content}
        </div>
        <div id="related-section">{related}</div>
      </article>
      <aside class="post-right-aside">
        <div class="post-aside-box">
          <div class="post-aside-title">// Share</div>
          <button class="share-btn" id="copy-link-btn" onclick="copyLink()">⎘ Copy link</button>
          <a class="share-btn" href="https://www.linkedin.com/sharing/share-offsite/?url={canonical_enc}" target="_blank" rel="noopener">in LinkedIn</a>
          <a class="share-btn" href="https://twitter.com/intent/tweet?url={canonical_enc}&amp;text={title_enc}" target="_blank" rel="noopener">𝕏 Twitter / X</a>
        </div>
        <div class="post-aside-box">
          <div class="post-aside-title">// The JeffOps Dispatch</div>
          <p style="font-family:var(--mono);font-size:0.7rem;color:var(--text-dim);line-height:1.6;margin-bottom:0.75rem;">Every other Monday, published on LinkedIn.</p>
          <a class="share-btn" style="background:var(--cyan-glow);border-color:var(--border);color:var(--cyan);" href="/#newsletter">Subscribe →</a>
        </div>
        <div class="post-aside-box">
          <div class="post-aside-title">// Progress</div>
          <div id="scroll-pct" style="font-family:var(--mono);font-size:1.4rem;font-weight:700;color:var(--cyan);">0%</div>
          <div style="height:3px;background:var(--bg3);margin-top:8px;border-radius:2px;">
            <div id="scroll-bar" style="height:100%;width:0%;background:var(--cyan);border-radius:2px;transition:width 0.1s;"></div>
          </div>
        </div>
      </aside>
    </div>
  </div>
</div>
</div><!-- /site-content -->
{footer}
<script src="https://cdnjs.cloudflare.com/ajax/libs/mermaid/10.6.1/mermaid.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
<script src="/js/post-page.js"></script>
</body>
</html>
"""


LIST_TEMPLATE = """<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Blog — {site_title}</title>
<meta name="description" content="{description}">
<link rel="canonical" href="{base_url}/posts/">
<meta property="og:type" content="website">
<meta property="og:url" content="{base_url}/posts/">
<meta property="og:title" content="Blog — {site_title}">
<meta property="og:description" content="{description}">
<meta property="og:image" content="{base_url}{og_image}">
<link rel="alternate" type="application/rss+xml" title="{site_title} Blog" href="{base_url}/rss.xml">
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32x32.png">
<link rel="icon" type="image/png" sizes="16x16" href="/favicon-16x16.png">
<link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png">
<link rel="mask-icon" href="/safari-pinned-tab.svg" color="#00d9ff">
<link rel="manifest" href="/site.webmanifest">
<meta name="msapplication-TileColor" content="#0a0c0f">
<meta name="theme-color" content="#0a0c0f">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/css/styles.css">
</head>
<body class="static-post">
{nav}
<div class="site-content">
<div class="page active">
  <div class="section">
    <div class="section-header"><span class="section-tag">// writing</span><h1 class="section-title">Blog</h1><div class="section-line"></div></div>
    <div class="post-list">
{items}
    </div>
  </div>
</div>
</div><!-- /site-content -->
{footer}
</body>
</html>
"""


def build_post_page(post: dict, by_folder: dict, nav: str, footer: str) -> str:
    content, toc = render_markdown(post['body_markdown'])
    canonical = canonical_for(post)
    article_meta = ''
    if post.get('iso'):
        article_meta = (f'<meta property="article:published_time" content="{post["iso"]}">\n'
                        + '\n'.join(f'<meta property="article:tag" content="{html.escape(t)}">'
                                    for t in post.get('tags', [])))
    tags_html = ''
    if post.get('tags'):
        chips = ''.join(f'<span class="tag">{html.escape(t)}</span>' for t in post['tags'])
        tags_html = f'<div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:10px;">{chips}</div>'

    # Every page on this site used to share one og:image, so a shared link to
    # any article previewed as the same generic card. A page with its own cover
    # now advertises that instead, and pages without one are unchanged.
    cover_html = ''
    og_image_url = SITE['base_url'] + SITE['og_image']
    if post.get('cover_url'):
        og_image_url = SITE['base_url'] + post['cover_url']
        # width and height are set so the browser reserves the right space
        # before the image loads. Without them the whole article jumps down the
        # moment it arrives, which is the single most irritating thing a page
        # can do to someone who has already started reading.
        dims = ''
        if post.get('cover_width') and post.get('cover_height'):
            dims = f' width="{post["cover_width"]}" height="{post["cover_height"]}"'
        cover_html = (
            '        <figure class="post-cover">'
            f'<img src="{html.escape(post["cover_url"], quote=True)}"'
            f' alt="{html.escape(post.get("cover_alt", ""))}"{dims}>'
            '</figure>'
        )

    return POST_TEMPLATE.format(
        lang=SITE['language'],
        title=html.escape(post['title']),
        title_enc=quote(post['title'], safe=''),
        site_title=SITE['title'],
        description=html.escape(meta_description(post)),
        author=html.escape(SITE['author']),
        canonical=canonical,
        canonical_enc=quote(canonical, safe=''),
        base_url=SITE['base_url'],
        og_image=SITE['og_image'],
        og_image_url=og_image_url,
        cover=cover_html,
        article_meta=article_meta,
        jsonld=json_ld(post),
        kicker='Newsletter Edition' if post.get('is_newsletter') else 'Blog Post',
        origin=edition_origin_note(post) if post.get('is_newsletter') else '',
        back_url='/#newsletter' if post.get('is_newsletter') else '/#blog',
        back_label='Back to the archive' if post.get('is_newsletter') else 'Back to Blog',
        nav=nav,
        footer=footer,
        toc=toc_html(toc),
        date=post['date'],
        readtime=post['readtime'],
        tags=tags_html,
        content=content,
        related=related_html(post, by_folder),
    )


def build_list_page(posts: list[dict], nav: str, footer: str) -> str:
    items = []
    for post in posts:
        chips = ''.join(f'<span class="tag">{html.escape(t)}</span>' for t in post.get('tags', []))
        chips_html = (f'<div style="display:flex;flex-wrap:wrap;gap:6px;margin:8px 0;">{chips}</div>'
                      if chips else '')
        items.append(
            f'      <div class="post-item">\n'
            f'        <div>\n'
            f'          <a class="post-title" href="{post["url"]}">{html.escape(post["title"])}</a>\n'
            f'          <div class="post-excerpt">{html.escape(post.get("excerpt", ""))}</div>\n'
            f'          {chips_html}\n'
            f'          <div class="post-meta"><span>{post["date"]}</span><span>{post["readtime"]}</span></div>\n'
            f'        </div>\n'
            f'        <div class="post-read-time">→</div>\n'
            f'      </div>'
        )
    return LIST_TEMPLATE.format(
        lang=SITE['language'],
        site_title=SITE['title'],
        description=html.escape(SITE['description']),
        base_url=SITE['base_url'],
        og_image=SITE['og_image'],
        nav=nav,
        footer=footer,
        items='\n'.join(items),
    )


# {content_class} is not cosmetic. `.post-content` is prose styling for markdown
# we generated ourselves: it sets a measure, and it restyles every img with
# `max-width:100%;height:auto;border;margin`. That is right for a screenshot in
# an article and wrong for markup lifted out of index.html, where the images are
# UI furniture. `.post-content img` (0,1,1) outranks `.avatar-image` (0,1,0), so
# the About avatar lost its `height:100%` and stopped being cropped by its
# circle, and the course logos on /training/ rendered at 177px with a border
# instead of 40px. Markdown pages keep `post-content`; lifted sections get
# `lifted-content`, which styles nothing and lets the site's own rules apply.
PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — {site_title}</title>
<meta name="description" content="{description}">
<meta name="author" content="{author}">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="website">
<meta property="og:url" content="{canonical}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta property="og:image" content="{base_url}{og_image}">
<meta property="og:site_name" content="{site_title}">
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32x32.png">
<link rel="icon" type="image/png" sizes="16x16" href="/favicon-16x16.png">
<link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png">
<link rel="mask-icon" href="/safari-pinned-tab.svg" color="#00d9ff">
<link rel="manifest" href="/site.webmanifest">
<meta name="msapplication-TileColor" content="#0a0c0f">
<meta name="theme-color" content="#0a0c0f">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/css/styles.css">
</head>
<body class="static-post">
{nav}
<div class="site-content">
<div class="page active">
  <div class="post-page-wrap">
    <div style="max-width:760px;margin:0 auto;padding-top:2rem;"><a class="back-btn" href="/">← Back to JeffOps</a></div>
    <article style="max-width:760px;margin:0 auto;">
      <div class="post-header">
        <div class="post-header-type">// {kicker}</div>
        <h1>{title}</h1>
      </div>
      <div class="{content_class}">
{content}
      </div>
    </article>
  </div>
</div>
</div><!-- /site-content -->
{footer}
</body>
</html>
"""


def build_standalone_pages(out: Path, nav: str, footer: str) -> list[str]:
    """Render every markdown file in pages/ to its own URL.

    Separate from posts on purpose. These are not articles: they carry no date,
    no author byline, no reading time and no share buttons, and they must stay
    out of the blog index, the RSS feed and the related-posts graph. Putting one
    in blog/ to reuse the post renderer would have published a security policy
    as an article and mailed it to every subscriber.
    """
    pages_dir = ROOT / 'pages'
    if not pages_dir.is_dir():
        return []

    # extract_shell highlights Content › Blog, which is right for a post and
    # wrong here: a security policy is not a blog post, and a lit nav item that
    # does not match the page is a small lie about where the reader is.
    nav = nav.replace(' class="active"', '')

    urls = []
    for source in sorted(pages_dir.glob('*.md')):
        raw = source.read_text(encoding='utf-8')
        front = parse_frontmatter(raw)
        slug = front.get('slug') or source.stem
        title = front.get('title') or parse_title(raw, source.stem)
        url = f'/{slug}/'
        content, _ = render_markdown(strip_leading_h1(raw))

        page_dir = out / slug
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / 'index.html').write_text(PAGE_TEMPLATE.format(
            lang=SITE['language'],
            site_title=SITE['title'],
            author=html.escape(SITE['author']),
            base_url=SITE['base_url'],
            og_image=SITE['og_image'],
            canonical=SITE['base_url'] + url,
            title=html.escape(title),
            kicker=html.escape(front.get('kicker', title)),
            description=html.escape(front.get('description', SITE['description'])),
            nav=nav,
            footer=footer,
            content_class='post-content',
            content=content,
        ), encoding='utf-8')
        urls.append(url)
    return urls


def write_security_txt(out: Path) -> bool:
    """Publish security.txt at both the required and the legacy path.

    RFC 9116 requires '/.well-known/security.txt' and permits a copy at the
    root for legacy consumers. The root copy is worth having here for a second
    reason: actions/upload-pages-artifact v4 and later strip dotfiles from the
    deploy artifact by default, so a misconfigured workflow silently deletes
    the '/.well-known/' directory and leaves a green build behind. The root copy
    still answers in that case.

    Both are written from the same source so they cannot drift apart, and both
    paths are listed in the file's own Canonical fields.
    """
    source = ROOT / '.well-known' / 'security.txt'
    if not source.exists():
        return False
    body = source.read_text(encoding='utf-8')
    (out / '.well-known').mkdir(parents=True, exist_ok=True)
    (out / '.well-known' / 'security.txt').write_text(body, encoding='utf-8')
    (out / 'security.txt').write_text(body, encoding='utf-8')
    return True



# ── Sections promoted to real URLs ────────────────────────────────────
#
# Consulting, Training, Speaking and About existed only as hash routes inside
# the single-page app, which means they had no URL, no title, no description
# and no presence in search at all. These are the pages that bring work in, so
# that is an odd place to be invisible.
#
# The content is lifted out of index.html rather than duplicated, so there is
# still one source of truth and the two can never disagree. The app keeps
# working exactly as before; this adds a crawlable copy underneath it, the same
# trick already used for blog posts.

PROMOTED_SECTIONS = {
    'consulting': {
        'title': 'Consulting',
        'kicker': 'services',
        'description': 'Platform engineering and enterprise IT consulting from Jeff '
                       'Wouters. Practical work on Azure, Kubernetes and developer '
                       'platforms, from inside a 25,000-user environment.',
    },
    'training': {
        'title': 'Training',
        'kicker': 'services',
        'description': 'Hands-on training in platform engineering, Kubernetes, Azure '
                       'and DevOps practice, delivered in person or remotely.',
    },
    'speaking': {
        'title': 'Speaking',
        'kicker': 'services',
        'description': 'Conference talks and workshops by Jeff Wouters on platform '
                       'engineering, developer experience and enterprise operations.',
    },
    'about': {
        'title': 'About',
        'kicker': 'about',
        'description': 'Jeff Wouters writes about platform engineering, AI-tomation '
                       'and enterprise IT from inside a 25,000-user environment, not '
                       'from a vendor deck.',
    },
}


def extract_section(index_html: str, section_id: str) -> str | None:
    """Lift one .page div out of index.html, balanced on nesting."""
    anchor = f'id="page-{section_id}"'
    if anchor not in index_html:
        return None
    start = index_html.rindex('<div', 0, index_html.index(anchor))
    depth, cursor = 0, start
    while True:
        token = re.search(r'<div\b|</div>', index_html[cursor:])
        if not token:
            return None
        depth += 1 if index_html[cursor + token.start(): cursor + token.end()].startswith('<div') else -1
        cursor += token.end()
        if depth == 0:
            return index_html[start:cursor]



def render_talks(talks: list[dict]) -> str:
    """Server-side copy of the talk list the app builds in the browser.

    Without this the promoted /speaking/ page is 500 characters of heading and
    a contact form: the talks themselves arrive by fetch and a crawler never
    sees them. It mirrors the markup in app.js exactly, so the page looks the
    same whether the script runs or not.
    """
    months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
              'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    items = []
    for talk in talks:
        try:
            when = datetime.fromisoformat(str(talk.get('date')))
            month, day, year = months[when.month - 1], f'{when.day:02d}', str(when.year)
        except (TypeError, ValueError):
            month = day = year = ''
        badge = (f'<span class="talk-badge '
                 f'{"badge-upcoming" if talk.get("status") == "Upcoming" else "badge-past"}">'
                 f'{html.escape(str(talk.get("statusLabel", "")))}</span>'
                 if talk.get('statusLabel') else '')
        links = ''.join(
            f'<a class="talk-link" href="{html.escape(str(l.get("href", "#")))}" '
            f'target="_blank" rel="noopener">{html.escape(str(l.get("label", "")))}</a>'
            for l in talk.get('links', []) if l.get('type') != 'abstract')
        items.append(
            '<div class="talk-item">'
            f'<div class="talk-date-col"><div class="talk-month">{month}</div>'
            f'<div class="talk-day">{day}</div><div class="talk-year">{year}</div></div>'
            '<div>'
            f'<div class="talk-event">{html.escape(str(talk.get("event", "")))} {badge}</div>'
            f'<div class="talk-title">{html.escape(str(talk.get("title", "")))}</div>'
            f'<div class="talk-location">📍 {html.escape(str(talk.get("location", "")))}</div>'
            f'<div class="talk-links">{links}</div>'
            '</div></div>')
    return ''.join(items)


def build_promoted_pages(out: Path, index_html: str, nav: str, footer: str,
                         talks: list[dict] | None = None) -> list[str]:
    # The app hides every .page that is not active, so a lifted section would
    # render invisible on its own URL. It also carries a fragment link back to
    # itself, which on a standalone page would go nowhere useful.
    plain_nav = nav.replace(' class="active"', '')
    urls = []
    for section_id, meta in PROMOTED_SECTIONS.items():
        block = extract_section(index_html, section_id)
        if not block:
            print(f'  ! No #{section_id} section found in index.html; skipping')
            continue
        content = block.replace(f'id="page-{section_id}" class="page"',
                                f'id="page-{section_id}"', 1)
        if section_id == 'speaking' and talks:
            content = content.replace('<div id="talks-list"></div>',
                                      f'<div id="talks-list">{render_talks(talks)}</div>', 1)
        content = _absolutise(content)
        url = f'/{section_id}/'
        page_dir = out / section_id
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / 'index.html').write_text(PAGE_TEMPLATE.format(
            lang=SITE['language'],
            site_title=SITE['title'],
            author=html.escape(SITE['author']),
            base_url=SITE['base_url'],
            og_image=SITE['og_image'],
            canonical=SITE['base_url'] + url,
            title=html.escape(meta['title']),
            kicker=html.escape(meta['kicker']),
            description=html.escape(meta['description']),
            nav=plain_nav,
            footer=footer,
            content_class='lifted-content',
            content=content,
        ), encoding='utf-8')
        urls.append(url)
    return urls


# ── Feeds and crawler files ───────────────────────────────────────────
def _rfc822(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
    except (ValueError, TypeError):
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return format_datetime(dt)


def build_rss(posts: list[dict]) -> str:
    items = []
    for post in posts:
        body, _ = render_markdown(post['body_markdown'])
        items.append(f"""  <item>
    <title>{html.escape(post['title'])}</title>
    <link>{canonical_for(post)}</link>
    <guid isPermaLink="true">{canonical_for(post)}</guid>
    <pubDate>{_rfc822(post.get('published_at') or post.get('iso', ''))}</pubDate>
    <description>{html.escape(post['description'])}</description>
    {''.join(f'<category>{html.escape(t)}</category>' for t in post.get('tags', []))}
    <content:encoded><![CDATA[{body.replace(']]>', ']]&gt;')}]]></content:encoded>
  </item>""")

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
  <title>{SITE['title']} — {SITE['tagline']}</title>
  <link>{SITE['base_url']}/</link>
  <atom:link href="{SITE['base_url']}/rss.xml" rel="self" type="application/rss+xml"/>
  <description>{html.escape(SITE['description'])}</description>
  <language>{SITE['language']}</language>
  <lastBuildDate>{_rfc822(posts[0].get('published_at') or posts[0]['iso']) if posts else format_datetime(datetime.now(timezone.utc))}</lastBuildDate>
{chr(10).join(items)}
</channel>
</rss>
"""


# Hash routes are not separate documents, so they do not belong in a sitemap.
# Only genuinely distinct URLs are listed.
def build_sitemap(posts: list[dict], extra_urls: list[str] | None = None) -> str:
    urls = [f"""  <url>
    <loc>{SITE['base_url']}/</loc>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
  </url>""", f"""  <url>
    <loc>{SITE['base_url']}/posts/</loc>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>"""]
    for post in posts:
        lastmod = f'\n    <lastmod>{post["iso"][:10]}</lastmod>' if post.get('iso') else ''
        urls.append(f"""  <url>
    <loc>{canonical_for(post)}</loc>{lastmod}
    <changefreq>monthly</changefreq>
    <priority>0.7</priority>
  </url>""")
    for url in extra_urls or []:
        urls.append(f"""  <url>
    <loc>{SITE['base_url']}{url}</loc>
    <changefreq>yearly</changefreq>
    <priority>0.3</priority>
  </url>""")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + '\n'.join(urls) + '\n</urlset>\n')


# ── Newsletter archive ────────────────────────────────────────────────
#
# Editions are written and published on LinkedIn first, then republished here.
# One markdown file per edition in newsletter/, frontmatter carrying the number,
# title, date, slug and the LinkedIn URL of the original.
#
# The body is the part that has to be carried across by hand, so an edition with
# no body is not a broken page — it is one that has not been brought over yet.
# It keeps its place in the archive and its entry keeps pointing at LinkedIn
# until a body exists. That means a half-migrated archive is a normal state
# rather than a failure, nothing empty can reach the site, and publishing an
# edition here is exactly one action: paste the text in.
#
# newsletter_editions.json is gone. It listed the same editions a second time,
# and a second copy of a fact is the copy that rots.

EDITION_DIR = ROOT / 'newsletter'
EDITION_PLACEHOLDER = 'TODO(jeff)'


def load_editions() -> list[dict]:
    """One folder per edition: the markdown, and the images it references.

    A folder rather than a loose file, so an edition's pictures live with the
    words that use them. The alternative was a shared image directory, which
    works right up until you want to know which of forty files still matters,
    or you delete an edition and leave its artwork behind forever.

    This is also how blog posts already work, and one convention for both
    beats two conventions for one thing each.
    """
    if not EDITION_DIR.is_dir():
        print('  ! newsletter/ not found — archive will be empty')
        return []

    editions = []
    for folder in sorted(p for p in EDITION_DIR.iterdir() if p.is_dir()):
        # A leading underscore marks a folder that is not an edition.
        if folder.name.startswith('_'):
            continue
        source = find_markdown_file(folder)
        if not source:
            print(f'  ! newsletter/{folder.name}/ has no markdown file; skipping')
            continue
        raw = source.read_text(encoding='utf-8')
        front = parse_frontmatter(raw)
        body = strip_frontmatter(raw).strip()

        # A body that is only the placeholder counts as no body at all. Checked
        # by marker rather than by length so that a stub someone half-edited
        # still cannot be mistaken for a finished edition.
        has_body = bool(body) and EDITION_PLACEHOLDER not in body

        title = front.get('title') or parse_title(raw, source.stem)
        date_iso = str(front.get('date', ''))[:10]
        try:
            shown = datetime.fromisoformat(date_iso).strftime('%b %d, %Y')
        except ValueError:
            shown = date_iso

        slug = front.get('slug') or slugify(title)
        linkedin = front.get('linkedin_url', '').strip()
        if not linkedin:
            print(f'  ! {source.name} has no linkedin_url; the original cannot be credited')

        edition = {
            'number': front.get('number', ''),
            'title': title,
            'date': shown,
            'date_iso': date_iso,
            'iso': f'{date_iso}T09:00:00' if date_iso else '',
            'slug': slug,
            'url': f'/newsletter/{slug}/',
            'linkedin_url': linkedin,
            'has_body': has_body,
            'source': f'{folder.name}/{source.name}',
            'folder_name': folder.name,
            'folder': f'newsletter/{slug}',
            'is_newsletter': True,
            'is_published': True,
            'tags': front.get('tags') or ['Newsletter'],
            'readtime': estimate_readtime(body) if has_body else '',
            'body_markdown': strip_leading_h1(body).strip() if has_body else '',
            'markdown': body if has_body else '',
            'description': front.get('description', '').strip()
                           or (parse_excerpt(body) if has_body else ''),
        }
        edition['excerpt'] = edition['description']
        attach_cover(edition, front, source)
        editions.append(edition)

    editions.sort(key=lambda e: e.get('date_iso', ''), reverse=True)
    return editions


def attach_cover(edition: dict, front: dict, source: Path) -> None:
    """Resolve the edition's cover image, if it has one.

    Declaring a cover that is not there is reported rather than ignored: a
    missing file would otherwise show as a broken image on the page and a dead
    og:image in every share card, neither of which anyone notices from the
    build log.

    Dimensions are measured from the file rather than declared in frontmatter.
    A number typed by hand is a number that goes stale the first time the image
    is re-exported, and a wrong one reserves the wrong space, which is worse
    than reserving none.
    """
    name = front.get('cover', '').strip()
    if not name:
        return

    # Resolved inside the edition's own folder, next to the markdown that
    # names it. Anchored to source.parent rather than joined blindly, so a
    # cover value containing .. cannot reach outside the folder.
    path = (source.parent / name).resolve()
    if source.parent.resolve() not in path.parents or not path.is_file():
        print(f'  ! {edition["source"]} declares cover "{name}", '
              f'which is not a file in newsletter/{source.parent.name}/')
        return

    alt = front.get('cover_alt', '').strip()
    if not alt:
        print(f'  ! {edition["source"]} has a cover with no cover_alt. '
              f'A decorative image needs alt=""; a meaningful one needs a description.')

    # The filename, not a Path. Edition records are serialised into
    # blog/index.json, and a Path is not JSON-serialisable: putting one here
    # took the whole build down. Keeping the record to plain strings means that
    # cannot happen again by accident.
    edition['cover_name'] = path.name
    edition['cover_url'] = f'{edition["url"]}{path.name}'
    edition['cover_alt'] = alt
    try:
        from PIL import Image
        with Image.open(path) as img:
            edition['cover_width'], edition['cover_height'] = img.size
    except Exception as exc:                       # Pillow missing, or not an image
        print(f'  ! could not read the dimensions of {path.name}: {exc}')


def edition_origin_note(edition: dict) -> str:
    """The 'this was published on LinkedIn first' block.

    Required on every republished edition, not decoration. The reader should be
    able to see where a piece first appeared and get to it in one click, and a
    search engine comparing two near-identical documents should find an explicit
    statement of which came first rather than having to guess.
    """
    if not edition.get('linkedin_url'):
        return ''
    return (
        '<div class="edition-origin">'
        '<span class="edition-origin-label">// originally published on LinkedIn</span>'
        f'<p>This edition of The JeffOps Dispatch was first published on LinkedIn on '
        f'{html.escape(edition["date"])}. This is a copy, kept here so it stays '
        f'readable without an account.</p>'
        f'<a class="edition-origin-link" href="{html.escape(edition["linkedin_url"], quote=True)}" '
        f'target="_blank" rel="noopener">Read the original on LinkedIn →</a>'
        '</div>'
    )


def build_edition_pages(out: Path, editions: list[dict], nav: str, footer: str) -> list[dict]:
    """Render every edition that has a body. Returns the ones rendered."""
    published = [e for e in editions if e['has_body']]
    for edition in published:
        page_dir = out / edition['url'].strip('/')
        page_dir.mkdir(parents=True, exist_ok=True)
        page = build_post_page(edition, {}, nav, footer)
        (page_dir / 'index.html').write_text(page, encoding='utf-8')
        # The cover sits next to the page it belongs to, the way a post's
        # assets do, so the URL in the markup and the file on disk cannot
        # drift apart.
        # Everything in the edition's folder except the markdown is an asset
        # it references, copied next to the rendered page exactly as a post's
        # assets are. That means a relative src in the body resolves too, not
        # only the declared cover.
        folder = ROOT / 'newsletter' / edition['folder_name']
        if folder.is_dir():
            for asset in sorted(folder.iterdir()):
                if asset.is_file() and asset.suffix.lower() not in ('.md', '.markdown'):
                    shutil.copy2(asset, page_dir / asset.name)
    return published


def render_editions(editions: list[dict]) -> str:
    """Build the archive list markup.

    Rendered here rather than fetched by the browser for the same reason posts
    are: these are links to published work, and a link that only exists after
    JavaScript runs is a link most crawlers never see.

    An edition that has been copied across links to its page on this site. One
    that has not still links to LinkedIn, and opens in a new tab because it is
    leaving the site. The two cases are visibly different: an off-site entry is
    marked, so the archive never pretends to hold something it does not.
    """
    if not editions:
        return '      <!-- No editions found in newsletter/. -->'

    rows = []
    for edition in editions:
        iso = edition.get('date_iso', '')
        shown = edition.get('date', '')
        number = f'#{int(edition["number"]):03d}' if str(edition.get('number', '')).isdigit() else ''
        on_site = edition.get('has_body')
        href = edition['url'] if on_site else edition.get('linkedin_url', '')
        if not href:
            continue
        target = '' if on_site else ' target="_blank" rel="noopener"'
        badge = ('' if on_site else
                 '<span class="issue-offsite">on LinkedIn</span>')
        rows.append(
            f'      <a class="issue-item" style="text-decoration:none;color:inherit;" '
            f'href="{html.escape(href, quote=True)}"{target}>'
            f'<div class="issue-num">{number}</div>'
            f'<div><div class="issue-title">{html.escape(edition["title"])}{badge}</div>'
            f'<time class="issue-date" datetime="{iso}">{shown}</time></div>'
            f'<div class="issue-arrow">→</div></a>'
        )
    return '\n'.join(rows)


ISSUE_LIST_RE = re.compile(
    r'(<div class="issue-list" id="issue-list">).*?(</div>)', re.DOTALL)


def inject_editions(index_html: str, editions: list[dict]) -> str:
    markup = render_editions(editions)
    result, count = ISSUE_LIST_RE.subn(
        lambda m: f'{m.group(1)}\n{markup}\n    {m.group(2)}', index_html, count=1)
    if not count:
        raise SystemExit('Could not find <div class="issue-list" id="issue-list"> '
                         'in index.html — the newsletter archive cannot be generated.')
    return result


# AI crawlers split three ways, and lumping them together is the mistake most
# robots.txt files make. A training crawler collects text to build a model. A
# retrieval agent fetches a page while answering someone's question right now,
# and cites it. A search crawler builds an index. Blocking the first does not
# block the other two, so a site can stay out of training corpora and still be
# read, quoted and linked in AI answers.
#
# Jeff's choice, 3 August 2026: block training, allow retrieval and search.
#
# Google-Extended is the subtle one. It governs Gemini and AI Overviews
# grounding only. It has no effect on ordinary Google Search ranking, and
# Googlebot is deliberately left alone below.
#
# None of this is enforcement. robots.txt is a request, honoured voluntarily,
# and a crawler that ignores it faces nothing here. It states the policy; it
# does not implement it.

AI_TRAINING_BOTS = [
    ('GPTBot', 'OpenAI, model training'),
    ('ClaudeBot', 'Anthropic, model training'),
    ('anthropic-ai', 'Anthropic, older training token'),
    ('Google-Extended', 'Google, Gemini and AI Overviews grounding only'),
    ('Applebot-Extended', 'Apple, model training'),
    ('CCBot', 'Common Crawl, the corpus most other models are built from'),
    ('FacebookBot', 'Meta, model training'),
    ('Amazonbot', 'Amazon, model training'),
    ('cohere-ai', 'Cohere, model training'),
]

# Crawl hard, send nothing back, and exist to aggregate or resell content.
SCRAPER_BOTS = [
    ('Bytespider', 'ByteDance'),
    ('omgili', 'Webz.io, content aggregation'),
    ('Diffbot', 'knowledge-graph extraction'),
    ('img2dataset', 'bulk image dataset collection'),
]

# Fetch a page to answer a question a person is asking, and link back. These are
# how the writing gets found, so they are welcome.
AI_RETRIEVAL_BOTS = [
    ('ChatGPT-User', 'OpenAI, browsing on a user request'),
    ('OAI-SearchBot', 'OpenAI, search index'),
    ('Claude-Web', 'Anthropic, browsing on a user request'),
    ('PerplexityBot', 'Perplexity, search index'),
    ('YouBot', 'You.com, search index'),
]


def build_robots() -> str:
    # Every comment is on its own line, never trailing a directive. RFC 9309
    # does allow an inline '#' and says the value ends there, but not every
    # crawler implements that: a naive parser reads the whole rest of the line
    # as the token, matches nothing, and the rule silently does nothing at all.
    # A rule that quietly fails is worse than no rule, because it looks present.
    def group(bots, note, rule):
        width = max(len(token) for token, _ in bots)
        lines = [f'# {note}', '#']
        lines += [f'#   {token.ljust(width)}   {why}' for token, why in bots]
        lines += [f'User-agent: {token}' for token, _ in bots]
        lines.append(rule)
        return '\n'.join(lines)

    return f"""# robots.txt for {SITE['base_url']}
#
# Search engines: welcome, all of it.
# AI training crawlers: no.
# AI retrieval agents answering a person's question: welcome.
#
# The distinction is deliberate. Being read, quoted and linked by an assistant
# is how people find this writing. Being swallowed into a training corpus is a
# different thing, and it is the one thing here that is declined.
#
# This file is a request. Crawlers honour it voluntarily.

User-agent: *
Allow: /

{group(AI_TRAINING_BOTS, 'Model training. Declined.', 'Disallow: /')}

{group(SCRAPER_BOTS, 'Bulk scrapers and aggregators. Heavy crawling, no referral value.', 'Disallow: /')}

{group(AI_RETRIEVAL_BOTS,
       'Retrieval and search agents. Welcome. These fetch a page to answer a'
       + chr(10) + '# question someone is asking and link back, which is how writing gets found.',
       'Allow: /')}

Sitemap: {SITE['base_url']}/sitemap.xml
"""


def build_og_card(path: Path) -> None:
    """Render the og-card the HTML has always referenced but never had."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print('  ! Pillow not installed — skipping og-card.png')
        return

    W, H = 1200, 630
    img = Image.new('RGB', (W, H), '#0a0c0f')
    draw = ImageDraw.Draw(img)

    def font(size, bold=True):
        for name in (('DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf'),):
            for base in ('/usr/share/fonts/truetype/dejavu/', '/usr/share/fonts/TTF/'):
                candidate = Path(base) / name
                if candidate.exists():
                    return ImageFont.truetype(str(candidate), size)
        return ImageFont.load_default()

    draw.rectangle([0, 0, W, 8], fill='#00D9FF')
    draw.text((80, 200), 'JeffOps.com', font=font(86), fill='#e8edf2')
    draw.text((80, 310), SITE['tagline'], font=font(44), fill='#00D9FF')
    draw.text((80, 400), 'Practical AI-tomation, platform engineering', font=font(30, False), fill='#9baab8')
    draw.text((80, 444), 'and enterprise ops — from inside the environment.', font=font(30, False), fill='#9baab8')
    draw.text((80, 530), 'Jeff Wouters', font=font(28), fill='#6b7a8d')
    img.save(path, 'PNG')
    print(f'  → {path.name}')


# ── Build ─────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description='Build JeffOps.com')
    parser.add_argument('--out', default='_site', help='output directory (default: _site)')
    parser.add_argument('--serve', nargs='?', const=8000, type=int, metavar='PORT',
                        help='serve the build on PORT (default 8000) after building')
    parser.add_argument('--preview', action='store_true',
                        help='also render scheduled and draft posts, banner-marked '
                             'and noindex. verify_build refuses to ship the result.')
    args = parser.parse_args()

    out = (ROOT / args.out).resolve()
    if out == ROOT:
        raise SystemExit('Refusing to build into the source directory.')

    print('Collecting posts…')
    now = utc_now()
    live = collect_posts(now=now)
    pending = unpublished_posts(now=now)

    # Editions that have been copied across are part of the site's writing, so
    # they join the blog index, the feed and the sitemap. Ones that have not are
    # still only on LinkedIn and appear nowhere but the archive list, pointing
    # there. One list, filtered once, so no consumer can disagree about which
    # editions exist here.
    editions = load_editions()
    on_site_editions = [e for e in editions if e['has_body']]
    writing = sorted(live + on_site_editions,
                     key=lambda item: item.get('iso', ''), reverse=True)

    # The client-side index is always written from the live set, even in preview.
    # It is a committed file, so letting a scheduled post into it would put the
    # full text of an unpublished piece into the repository's own output.
    write_index_files(writing)
    posts = live
    live_urls = {p['url'] for p in posts}
    if args.preview:
        extra = [p for p in collect_posts(include_unpublished=True, now=now)
                 if p['url'] not in live_urls]
        posts = posts + extra
    if pending:
        print(f'{len(pending)} post(s) not published yet:')
        report_schedule(pending)

    # A duplicate URL means two posts would overwrite each other — fail loudly
    # rather than silently publishing one of them. Editions are checked in the
    # same pass: two editions sharing a slug, or an edition colliding with a
    # post, is the same failure and must not be discovered in production.
    seen: dict[str, str] = {}
    for post in posts + on_site_editions:
        if post['url'] in seen:
            raise SystemExit(f'Duplicate URL {post["url"]}: '
                             f'"{seen[post["url"]]}" and "{post["folder"]}". '
                             f'Set a distinct slug in the frontmatter of one of them.')
        seen[post['url']] = post['folder']

    by_folder = {post['folder']: post for post in posts}
    nav, footer = extract_shell((ROOT / 'index.html').read_text(encoding='utf-8'))

    if out.exists():
        try:
            shutil.rmtree(out)
        except OSError as exc:
            # A file in the output can be locked — an editor holding it open, a
            # virus scanner, a synced folder. Carry on rather than dying, but say
            # so clearly: without a clean wipe, a post that was renamed or deleted
            # can leave a stale page behind. CI always builds on a fresh runner,
            # so this only ever affects a local preview.
            print(f'  ! Could not fully clear {out.name}: {exc}')
            print('  ! Continuing over the existing output — stale files may remain.')
    out.mkdir(parents=True, exist_ok=True)

    print(f'Copying static assets → {out.name}/')
    for name in STATIC_ASSETS:
        src = ROOT / name
        if not src.exists():
            continue
        if src.is_dir():
            # dirs_exist_ok matters only when the wipe above was refused; on a
            # clean build the destination never exists.
            shutil.copytree(src, out / name, dirs_exist_ok=True)
        else:
            shutil.copy2(src, out / name)

    for pattern in ROOT_ASSET_PATTERNS:
        for item in sorted(ROOT.glob(pattern)):
            if item.is_file():
                shutil.copy2(item, out / item.name)

    # static/ is flattened into the site root, the way Hugo served it, so every
    # icon URL the old site published resolves unchanged.
    static_dir = ROOT / 'static'
    if static_dir.is_dir():
        for item in sorted(static_dir.iterdir()):
            if item.is_file():
                shutil.copy2(item, out / item.name)

    print(f'Rendering {len(posts)} post pages…')
    for post in posts:
        page_dir = out / post['url'].strip('/')
        page_dir.mkdir(parents=True, exist_ok=True)
        page = build_post_page(post, by_folder, nav, footer)
        if not post.get('is_published', True):
            when = post['published_at'][:16].replace('T', ' ') + ' UTC'
            page = page.replace('<head>',
                                '<head>\n<meta name="robots" content="noindex,nofollow">', 1)
            page = page.replace('<div class="post-content" id="post-content">',
                                '<div class="post-content" id="post-content">\n'
                                + PREVIEW_BANNER.format(when=when), 1)
        (page_dir / 'index.html').write_text(page, encoding='utf-8')

        # Anything else in the post's folder is an asset it references. Copying
        # it next to the rendered page means a relative src in the markdown
        # resolves both on the static page and in the single-page app, without
        # the author having to think about where the file will end up.
        source_dir = ROOT / post['folder']
        if source_dir.is_dir():
            for asset in sorted(source_dir.iterdir()):
                if asset.is_file() and asset.suffix.lower() not in ('.md', '.markdown'):
                    shutil.copy2(asset, page_dir / asset.name)
        print(f'  → {post["url"]}' + ('   [preview, not live]'
                                      if not post.get('is_published', True) else ''))

    copy_blog(out, live)

    rendered = build_edition_pages(out, editions, nav, footer)
    for edition in rendered:
        print(f'  → {edition["url"]}')
    waiting = [e for e in editions if not e['has_body']]
    if waiting:
        print(f'{len(waiting)} edition(s) not copied across yet, still linking to LinkedIn:')
        for edition in waiting:
            print(f'  · #{edition["number"]} {edition["title"]}  ({edition["source"]})')

    index_source = (ROOT / 'index.html').read_text(encoding='utf-8')

    talks_file = ROOT / 'speaking_talks.json'
    talks = json.loads(talks_file.read_text(encoding='utf-8')) if talks_file.exists() else []
    if isinstance(talks, dict):
        talks = talks.get('talks', [])
    talks = normalise_talks(talks)
    (out / 'speaking_talks.json').write_text(
        json.dumps(talks, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    upcoming = sum(1 for t in talks if t['status'] == 'Upcoming')
    print(f'Normalised {len(talks)} talk(s): {upcoming} upcoming, {len(talks) - upcoming} past')

    index_source = inject_editions(index_source, editions)

    problems: list[str] = []
    cells, declared = build_stat_cells(live, talks, editions, problems.append)
    for problem in problems:
        print(f'  ! {problem}')
    index_source = inject_stats(index_source, cells)
    index_source = inject_events(index_source)
    index_source = inject_counts(index_source, live, talks)
    index_source = inject_home_meta(index_source, live)
    total = cells.count('stat-cell')
    print(f'Injected {total} home page statistic(s): {total - declared} derived, '
          f'{declared} declared in stats.json')

    (out / 'index.html').write_text(index_source, encoding='utf-8')
    print(f'Injected {len(editions)} newsletter edition(s) into index.html')

    page_urls = build_standalone_pages(out, nav, footer)
    page_urls += build_promoted_pages(out, index_source, nav, footer, talks)
    for url in page_urls:
        print(f'  → {url}')

    redirects = load_redirects()
    if redirects:
        taken = {p['url'] for p in posts} | {u for u in page_urls} | {'/posts/', '/'}
        done = write_redirects(out, redirects, taken)
        print(f'Wrote {len(done)} redirect(s) for URLs the old site published')

    if write_security_txt(out):
        print('Published security.txt at /.well-known/ and at the root')
    else:
        print('  ! No .well-known/security.txt in the source tree — nothing published')

    (out / 'posts').mkdir(parents=True, exist_ok=True)
    (out / 'posts' / 'index.html').write_text(build_list_page(live, nav, footer), encoding='utf-8')
    feed = build_rss(writing)
    (out / 'rss.xml').write_text(feed, encoding='utf-8')
    # Hugo published the feed at /index.xml for years. Anyone still subscribed
    # points there, and a feed reader that meets a redirect may simply drop the
    # subscription, so the same bytes are served at the old path too.
    (out / 'index.xml').write_text(feed, encoding='utf-8')
    (out / 'sitemap.xml').write_text(build_sitemap(writing, page_urls), encoding='utf-8')
    (out / 'robots.txt').write_text(build_robots(), encoding='utf-8')
    (out / 'CNAME').write_text('jeffops.com\n', encoding='utf-8')

    # GitHub Pages runs Jekyll by default and skips files starting with _.
    (out / '.nojekyll').write_text('', encoding='utf-8')

    og_source = ROOT / 'og-card.png'
    if og_source.exists():
        shutil.copy2(og_source, out / 'og-card.png')
    else:
        build_og_card(out / 'og-card.png')

    print(f'\nBuilt {len(live)} published post(s) into {out}'
          + (f', plus {len(posts) - len(live)} preview page(s)' if args.preview else ''))
    if args.preview:
        print('This is a PREVIEW build. verify_build will refuse it, by design.')

    if args.serve:
        serve(out, args.serve)


def serve(directory: Path, port: int) -> None:
    """Serve the build locally.

    This exists because opening the output with file:// does not work and cannot
    be made to work. Every asset path and every link between pages is
    root-absolute, which is correct for a deployed site and meaningless on a
    filesystem — under file:// a leading slash resolves to the drive root, so
    the stylesheet 404s and every link lands nowhere. Relative paths would fix
    the stylesheet but not the links, because a directory URL under file://
    shows a directory listing instead of its index.html.

    So: a real server, on a real port, the way the site will actually be served.
    """
    import functools
    import http.server
    import socketserver

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(('', port), handler) as httpd:
        print(f'\nServing {directory} at http://localhost:{port}/')
        print(f'  Blog index   http://localhost:{port}/posts/')
        print('  Ctrl-C to stop.')
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print('\nStopped.')


if __name__ == '__main__':
    main()
