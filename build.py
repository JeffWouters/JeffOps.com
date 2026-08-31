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
                                 is_draft, parse_excerpt, parse_frontmatter, parse_title, slugify,
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
STATIC_ASSETS = ['index.html', 'css', 'js', 'vendor', 'logos', 'speaking_topics.json']

# Images in the project root are copied by pattern rather than by name. The list
# above used to carry 'JeffOps_Speaking.jpg' literally, so a second photo added
# next to it was simply never copied, and the page referencing it would have
# shown a broken image with nothing anywhere reporting a problem.
ROOT_ASSET_PATTERNS = ('*.jpg', '*.jpeg', '*.png', '*.webp', '*.svg', '*.gif')

MD_EXTENSIONS = ['fenced_code', 'tables', 'attr_list', 'sane_lists', 'toc', 'footnotes']
MD_CONFIG = {'toc': {'permalink': False, 'toc_depth': '2-3'}}



# ── Publication ───────────────────────────────────────────────────────
BLOG_INDEX_FILES = ('index.json', 'index.js', 'topics.json', 'series.json')

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
    # Markdown only. The images a post references are already published beside
    # its rendered page, and the single-page app resolves relative sources
    # against the post's URL rather than its source folder, so copying the
    # binaries here published a second copy of every featured image that
    # nothing ever requested — 194KB for the reMarkable post alone.
    for post in posts:
        folder = ROOT / post['folder']
        if not folder.is_dir():
            continue
        target = out / post['folder']
        target.mkdir(parents=True, exist_ok=True)
        for item in sorted(folder.iterdir()):
            if item.is_file() and item.suffix.lower() in ('.md', '.markdown'):
                shutil.copy2(item, target / item.name)


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
<!-- Delivered as a meta element because GitHub Pages cannot set response
     headers. Two consequences worth knowing: frame-ancestors is ignored in
     meta, so clickjacking is not mitigated here, and there is no way to set
     HSTS, COOP or X-Frame-Options at all. Those need a proxy in front.
     style-src keeps 'unsafe-inline' for the 55 style attributes in the
     markup; a CSS injection cannot execute script, and script-src carries
     no such escape hatch. cdnjs is allowed for one reason: Mermaid, fetched
     on demand and only for a page that has a diagram. -->
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; base-uri 'none'; object-src 'none'; frame-src 'none'; form-action 'none'; script-src 'self' https://cdnjs.cloudflare.com; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; manifest-src 'self'; require-trusted-types-for 'script'">
<title>{site_title} — Moved</title>
<link rel="canonical" href="{absolute}">
<meta http-equiv="refresh" content="0; url={target}">
<meta name="robots" content="noindex, follow">
</head>
<body style="font-family:system-ui,sans-serif;background:#0a0c0f;color:#e8edf2;padding:3rem">
<!-- The meta refresh above does the redirect. An inline script used to do it
     as well, and the Content Security Policy blocks inline script — so it had
     stopped running the moment that policy shipped, silently, while the meta
     refresh carried on working and hid it. -->
<main>
<p>This page has moved to <a style="color:#00d9ff" href="{target}">{target}</a>.</p>
</main>
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


def rotate_portrait(index_html: str, now: datetime, out: Path) -> str:
    """Pick which of the portraits this build ships.

    The app used to do this in the browser, per visit: the markup carried one
    photograph and JavaScript swapped in one of three at random, so two thirds
    of visits downloaded a second portrait — 35 to 55KB never shown — and the
    picture visibly changed once it arrived.

    Choosing here costs nothing and shows one image. The rotation survives:
    the build runs daily, and the day number selects the photograph, so the
    site still changes its face — once a day rather than once a reload.
    """
    match = re.search(r'data-portraits="([^"]+)"', index_html)
    if not match:
        return index_html
    options = [p.split('|', 1) for p in match.group(1).split(',') if p.strip()]
    options = [(s.strip(), (a[0] if a else '').strip()) for s, *a in options]
    if len(options) < 2:
        return index_html
    src, alt = options[now.toordinal() % len(options)]

    # Now that one photograph is chosen for the whole build rather than swapped
    # in the browser, it can be offered as WebP the same way covers are. A
    # <source> would have lost that race against a JS-assigned src.
    # narrow=True, like every content image. Without it this was the only picture on the site
    # offered as a single candidate with no widths and no sizes: one 750px file served a 374px hero,
    # a ~193px hero, a ~104px phone hero and the fixed 100px avatar on /about/, where it is the only
    # image on the page and therefore its entire image budget.
    webp = write_webp(out / src, narrow=True) if (out / src).exists() else None

    def swap(m: re.Match) -> str:
        tag = m.group(0)
        tag = re.sub(r'\ssrc="[^"]*"', f' src="{html.escape(src, quote=True)}"', tag)
        if alt:
            tag = re.sub(r'\salt="[^"]*"', f' alt="{html.escape(alt, quote=True)}"', tag)
        if webp:
            webp_set = srcset_for(out, src, '.webp') or html.escape(webp, quote=True)
            jpeg_set = srcset_for(out, src, Path(src).suffix)
            if jpeg_set and ' ' in jpeg_set:
                tag = tag[:-1].rstrip().rstrip('/').rstrip() + \
                      f' srcset="{jpeg_set}" sizes="{PORTRAIT_SIZES}">'
            return (f'<picture><source srcset="{webp_set}" sizes="{PORTRAIT_SIZES}" '
                    f'type="image/webp">{tag}</picture>')
        return tag

    updated = re.sub(r'<img\b[^>]*\bdata-portraits="[^"]*"[^>]*>', swap, index_html)
    size = (out / src).stat().st_size if (out / src).exists() else 0
    print(f'Portrait for this build: {src} ({size} bytes'
          + (f', WebP {(out / webp).stat().st_size}' if webp else '') + ')')
    return updated


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
        # Taken from the role line on the About page. Search engines read this
        # field, so it disagreeing with what the page says is the kind of drift
        # nothing reports.
        'jobTitle': 'CTO',
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
    # srcset belongs in this alternation. It was missing, and the omission was invisible until the
    # portrait gained a WebP sibling: choose_portrait() wraps the avatar in
    # <picture><source srcset="JeffOps_Finger.webp">, and on /about/ the <img src> was absolutised
    # while the <source srcset> stayed bare, resolving to /about/JeffOps_Finger.webp — a 404, while
    # the file sits at the root. A browser that has already MATCHED a <source> does not fall back to
    # the <img> when its resource fails, so the avatar painted nothing for every WebP-capable
    # visitor. verify_build.py states that exact rule in its own comments, but only applied it
    # inside the post loop, so this shipped green.
    fragment = re.sub(r'(href|src|srcset)="(?!https?://|//|/|#|mailto:|data:)', r'\1="/', fragment)
    fragment = re.sub(r'href="#(?!")', 'href="/#', fragment)
    return fragment


def current_year(index_html: str, now: datetime) -> str:
    """Move the footer's copyright year forward to the year of the build.

    The footer read '© 2024' well into 2026 for the obvious reason: a literal
    year in a source file is a fact that has to be remembered, and nobody
    remembers it. The build knows the date, so it sets it. index.html keeps a
    real year rather than a placeholder so the file still renders correctly if
    it is opened on its own.
    """
    return re.sub(r'(©\s*)\d{4}', lambda m: m.group(1) + str(now.year), index_html)


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
    return render_callouts(wrap_figures(reachable_code_blocks(body))), toc


# GitHub's blockquote callout syntax. Rendered here rather than in the browser
# so the crawled HTML carries the real markup instead of a blockquote that opens
# with a literal "[!WARNING]". js/post-enhance.js holds the SPA's copy of this —
# the class names and this type list are the contract between them.
CALLOUT_TYPES = {'NOTE': 'Note', 'TIP': 'Tip', 'IMPORTANT': 'Important',
                 'WARNING': 'Warning', 'CAUTION': 'Caution'}

_CALLOUT_RE = re.compile(
    r'<blockquote>\s*<p>\s*\[!([A-Z]+)\]\s*(?:<br\s*/?>)?\s*',
    re.IGNORECASE)


def render_callouts(html_text: str) -> str:
    def replace(match: re.Match) -> str:
        kind = match.group(1).upper()
        if kind not in CALLOUT_TYPES:
            return match.group(0)
        return (f'<blockquote class="callout callout-{kind.lower()}">'
                f'<div class="callout-label">{CALLOUT_TYPES[kind]}</div><p>')

    return _CALLOUT_RE.sub(replace, html_text)


# How long a technical post is allowed to sit unreviewed before the page says so
# out loud. Platform tooling moves fast enough that a year-old walkthrough is
# often wrong; the banner does not claim the post is wrong, only that nobody has
# checked. Change this number and every page re-evaluates on the next build.
STALE_AFTER_DAYS = 365


def freshness(post: dict, now: datetime) -> tuple[str, str]:
    """Return (meta line HTML, banner HTML) for a post's age."""
    reviewed = post.get('reviewed') or post.get('iso') or ''
    if not reviewed:
        return '', ''
    try:
        reviewed_dt = datetime.fromisoformat(reviewed[:19])
    except ValueError:
        return '', ''
    label = post.get('reviewed_label') or ''
    meta = ''
    if label and label != post.get('date'):
        meta = f'<span class="post-reviewed">Reviewed {html.escape(label)}</span>'
    age = (now.replace(tzinfo=None) - reviewed_dt).days
    # A newsletter edition is a dated dispatch, not a document anyone maintains.
    # Telling a reader that a piece from last spring has not been revised since
    # last spring is noise, so the banner is for posts only.
    if age <= STALE_AFTER_DAYS or post.get('is_newsletter'):
        return meta, ''
    years = age / 365.0
    when = f'{age} days' if years < 1 else (
        'over a year' if years < 2 else f'over {int(years)} years')
    banner = (
        '<aside class="stale-note">'
        f'<strong>This post has not been reviewed in {when}.</strong> '
        'It was accurate when written. Version numbers, menu paths and vendor '
        'behaviour all move, so check anything you are about to depend on.'
        '</aside>'
    )
    return meta, banner


def series_nav(post: dict, by_series: dict) -> str:
    """Previous/next within a series, and where this post sits in it.

    Driven entirely by the `series:` line in a post's frontmatter. No posts
    carry one yet, so this renders nothing until two of them share a value.
    """
    key = post.get('series')
    members = by_series.get(key) or []
    if not key or len(members) < 2:
        return ''
    try:
        idx = next(i for i, item in enumerate(members) if item['url'] == post['url'])
    except StopIteration:
        return ''
    label = html.escape(post.get('series_label') or key)
    prev_item = members[idx - 1] if idx > 0 else None
    next_item = members[idx + 1] if idx + 1 < len(members) else None
    links = ''
    if prev_item:
        links += (f'<a class="series-link" href="{prev_item["url"]}" rel="prev">'
                  f'‹ {html.escape(prev_item["title"])}</a>')
    if next_item:
        links += (f'<a class="series-link" href="{next_item["url"]}" rel="next">'
                  f'{html.escape(next_item["title"])} ›</a>')
    return (f'<nav class="series-nav" aria-label="Series navigation">'
            f'<div class="series-nav-head">'
            f'<span class="series-nav-label">// {label}</span>'
            f'<span class="series-nav-count">Part {idx + 1} of {len(members)}</span>'
            f'</div>'
            f'<div class="series-nav-links">{links}</div></nav>')


def write_markdown_source(page_dir: Path, post: dict) -> None:
    """Publish the post's markdown next to its HTML.

    This is what the Copy as Markdown button fetches, and it doubles as a plain
    source anyone — or anything — can read without parsing the page. The header
    is two comment lines rather than frontmatter so that pasting the file
    somewhere shows the attribution instead of hiding it in metadata.
    """
    body = (post.get('markdown') or '').strip()
    if not body:
        return
    header = (f'<!-- {canonical_for(post)}\n'
              f'     {post["title"]} — {SITE["author"]}, {post["date"]} -->\n\n')
    (page_dir / 'index.md').write_text(header + body + '\n', encoding='utf-8')


def group_series(posts: list[dict]) -> dict:
    """series key → its posts, oldest first, which is the order they are read in."""
    grouped: dict[str, list[dict]] = {}
    for post in posts:
        key = post.get('series')
        if key:
            grouped.setdefault(key, []).append(post)
    for members in grouped.values():
        members.sort(key=lambda item: item.get('iso', ''))
    return grouped


def reachable_code_blocks(html: str) -> str:
    """Make a scrolling <pre> reachable from a keyboard.

    .post-content pre is overflow-x:auto with no focusable descendant, so a mouse can pan a long
    line and a keyboard cannot reach it at all — axe-core's scrollable-region-focusable, WCAG 2.1.1.
    The overflow is real: the longest line on the site is 90 characters against a content box around
    596px, which needs roughly 734px.

    role=group rather than region, because eighteen landmarks on one page is worse than none, and a
    group still carries the name into the accessibility tree.
    """
    return re.sub(r'<pre(?![^>]*\btabindex=)',
                  '<pre tabindex="0" role="group" aria-label="Code, scrollable"',
                  html)


def wrap_figures(html: str) -> str:
    """Put each inline SVG in its own scroll container.

    An SVG scaled to a phone-width column shrinks its labels to about four
    pixels, which is a diagram that technically fits and cannot be read. The
    wrapper lets the figure keep a legible minimum width and scroll sideways on
    its own, instead of scaling to nothing or dragging the whole page into
    horizontal scroll. Feed readers that ignore the class simply see the SVG in
    a div, which is what they saw before.
    """
    # tabindex and a name, because a region that scrolls has to be scrollable from a keyboard. That
    # is axe-core's scrollable-region-focusable, WCAG 2.1.1, and the overflow here is guaranteed
    # rather than hypothetical: .figure-scroll svg carries min-width:640px inside a column narrower
    # than 640px at that breakpoint. The obvious escape hatch does not apply — the copy button that
    # would give the region focusable content is added only in the single-page view, and a static
    # post page never loads it.
    return re.sub(r'(<svg\b.*?</svg>)',
                  r'<div class="figure-scroll" tabindex="0" role="group" '
                  r'aria-label="Diagram, scrollable">\1</div>',
                  html, flags=re.DOTALL)


# ── WebP variants ─────────────────────────────────────────────────────
#
# A WebP is written beside each photograph the site displays, and the page
# offers it through <picture> with the original JPEG as the fallback. Browsers
# that want it take it; everything else, including the link preview crawlers,
# still sees a JPEG at the same URL it always had.
#
# JPEG only, deliberately. The PNGs here are logos, icons and the share card:
# small, alpha-sensitive, and og:image must stay a format LinkedIn and X will
# accept, which WebP is not. Ten kilobytes is not worth that class of risk.
#
# 86 was chosen by measuring: SSIM stays at or above 0.97 against the original
# on every photograph on the site, while the covers lose about 45% of their
# bytes. Lower starts to show on the flat backgrounds in the newsletter art.
WEBP_QUALITY = 86
WEBP_MIN_BYTES = 20_000
# What write_webp will convert. PNG was absent until 2026-08-31, so no PNG on the site had ever
# been given a WebP sibling while every JPEG had — the gap was invisible because the four earlier
# newsletter editions all led with a JPEG cover. The fifth used three PNG diagrams instead and
# shipped 629 KB with no WebP at all.
WEBP_SOURCES = ('.jpg', '.jpeg', '.png')

# The article column is 760px wide, so a 1200px cover is nearly twice what a
# non-retina screen renders. This is the second width offered; the browser picks
# by its own device pixel ratio, so a retina screen still gets the original and
# everyone else stops paying for pixels they cannot see.
NARROW_WIDTH = 760
CONTENT_SIZES = '(max-width: 800px) 100vw, 760px'
# The portrait is a circular hero on the home page and a small fixed avatar on /about/, so it is
# never the width of the content column. Telling the browser that is the whole point of sizes:
# without it a srcset is guesswork and it assumes the full viewport.
PORTRAIT_SIZES = '(max-width: 700px) 40vw, 374px'


def write_webp(image_path: Path, narrow: bool = False) -> str | None:
    """Write a sibling .webp, and optionally a narrower pair beside it.

    Returns the WebP filename, or None if not worth it. When `narrow` is set and
    the image is wide enough to be worth halving, `<stem>-760.webp` and
    `<stem>-760.jpg` are written too, for the srcset the page will offer.
    """
    if image_path.suffix.lower() not in WEBP_SOURCES:
        return None
    # Whether a WebP is worth writing and whether a 760w variant is worth writing are different
    # questions, and this threshold used to answer both. An image can be large in pixels and small
    # in bytes — which is exactly what a flat screenshot is. 10-policy-live.jpg is 1502x818 at
    # 11,702 B and was the only one of that post's screenshots with no WebP, no -760 sibling and no
    # srcset at all, so a reader on a 760px column downloaded 1502px of it.
    worth_full = image_path.stat().st_size >= WEBP_MIN_BYTES

    # PNG is encoded LOSSLESSLY, JPEG lossily, and that split is measured rather than assumed.
    # A PNG is here because someone needed flat colour, hard edges, text or transparency — a
    # diagram, a screenshot, a logo — which is the content lossy WebP handles worst. On the
    # newsletter diagrams that prompted this, quality 82 was 68% smaller but put a peak error of
    # 32/255 on text edges, which is visible ringing on small anti-aliased type; quality 90 was
    # dominated outright, nearly the same error for 28% more bytes. Lossless is 45% smaller than
    # the PNG and pixel-identical, and these images exist to be read.
    #
    # A photograph saved as PNG would be better served lossily, but the site has none: PNG here
    # means diagram, and guessing per image would be a worse rule than the one the file extension
    # already states.
    lossless = image_path.suffix.lower() == '.png'
    encode = dict(lossless=True, method=6) if lossless else dict(quality=WEBP_QUALITY, method=6)

    target = image_path.with_suffix('.webp')
    try:
        from PIL import Image
        with Image.open(image_path) as im:
            # The full-size WebP is gated on bytes; the responsive pair is gated on pixels, which
            # is the measurement that decides whether a 760px column is being sent more image than
            # it can use.
            if worth_full:
                im.save(target, 'WEBP', **encode)
            if narrow and im.width > NARROW_WIDTH * 1.2:
                small = im.copy()
                small.thumbnail((NARROW_WIDTH, im.height), Image.LANCZOS)
                small.save(image_path.with_name(f'{image_path.stem}-{NARROW_WIDTH}.webp'),
                           'WEBP', **encode)
                # The narrow fallback keeps the source's own format, which matters for PNG: these
                # diagrams have transparent rounded corners, and a JPEG fallback would put black
                # ones on the page. Pillow ignores quality and progressive when writing PNG.
                small.save(image_path.with_name(f'{image_path.stem}-{NARROW_WIDTH}{image_path.suffix}'),
                           quality=WEBP_QUALITY, optimize=True, progressive=True)
    except Exception as exc:                          # noqa: BLE001
        print(f'  ! {image_path.name}: WebP encode failed ({exc}) — JPEG only')
        return None
    # A WebP that is not smaller is a second file for nothing.
    if not target.exists():
        # Under the byte threshold, so only the responsive pair was written. offer_webp() needs a
        # name to build a <source> from, and srcset_for() skips widths that were not written, so
        # returning the name of a file that does not exist would produce a <source> pointing at
        # nothing — which is the exact failure that blanked the About avatar.
        return target.name if image_path.with_name(
            f'{image_path.stem}-{NARROW_WIDTH}.webp').exists() else None
    if target.stat().st_size >= image_path.stat().st_size:
        target.unlink()
        return None
    return target.name


def srcset_for(page_dir: Path, filename: str, suffix: str) -> str:
    """`x-760.ext 760w, x.ext 1200w`, skipping widths that were not written."""
    stem = filename.rsplit('.', 1)[0]
    parts = []
    narrow = page_dir / f'{stem}-{NARROW_WIDTH}{suffix}'
    if narrow.is_file():
        parts.append(f'{narrow.name} {NARROW_WIDTH}w')
    full = page_dir / f'{stem}{suffix}'
    if full.is_file():
        try:
            from PIL import Image
            with Image.open(full) as im:
                parts.append(f'{full.name} {im.width}w')
        except Exception:                             # noqa: BLE001
            pass
    return ', '.join(parts)


_IMG_RE = re.compile(r'<img\b[^>]*?\bsrc="([^"]+)"[^>]*>')


def size_images(markup: str, page_dir: Path) -> str:
    """Give every local <img> its real width and height.

    An image with no dimensions occupies nothing until it arrives, so the text
    below it is laid out twice and jumps when the picture lands. The cover
    figure has carried width and height for a while; images written in markdown
    never have, which is where the 0.06 of layout shift on a post page was
    coming from.
    """
    # Loading priority is decided here too, because this is the only pass that sees the images of a
    # page in document order. Every image was eager: on the MTA-STS post that is 211 KB at DPR1 and
    # 605 KB at DPR2 fetched before the reader has left the first paragraph, for pictures that begin
    # 1,116 words into a 2,419-word body. js/trusted-types.js already allowlists `loading` and
    # `fetchpriority` in its DOMPurify config, so the sanitiser was expecting attributes the build
    # never emitted.
    #
    # The FIRST image on a page stays eager and is marked high priority: on the reMarkable post the
    # featured image is the first body element and is the LCP, and lazy-loading the LCP is the
    # classic way to make this change a regression instead of a fix.
    seen = 0

    def add(match: re.Match) -> str:
        nonlocal seen
        tag, src = match.group(0), match.group(1)
        if src.startswith(('http', 'data:', '//')):
            return tag
        path = (page_dir / src.lstrip('/')) if src.startswith('/') else (page_dir / src)
        if not path.is_file():
            return tag

        extra = ''
        if 'width=' not in tag:
            try:
                from PIL import Image
                with Image.open(path) as im:
                    w, h = im.size
                extra += f' width="{w}" height="{h}"'
            except Exception:                             # noqa: BLE001
                pass

        seen += 1
        if 'loading=' not in tag and 'fetchpriority=' not in tag:
            extra += ' fetchpriority="high"' if seen == 1 else ' loading="lazy"'
        if 'decoding=' not in tag:
            extra += ' decoding="async"'
        if not extra:
            return tag
        # python-markdown closes img tags XHTML-style, so the trailing slash has
        # to come off before anything is appended or it lands mid-attribute.
        return tag[:-1].rstrip().rstrip('/').rstrip() + extra + '>'

    return _IMG_RE.sub(add, markup)


def offer_webp(markup: str, available: set[str], page_dir: Path | None = None) -> str:
    """Wrap <img> in <picture> where a WebP sibling was written.

    Only rewrites images whose src is a bare filename in the page's own folder,
    which is what a post's markdown produces. Anything absolute or reaching
    into another directory is left alone rather than guessed at.
    """
    if not available:
        return markup

    def wrap(match: re.Match) -> str:
        tag, src = match.group(0), match.group(1)
        if '/' in src or src not in available:
            return tag
        suffix = '.' + src.rsplit('.', 1)[1]
        webp = srcset_for(page_dir, src, '.webp') if page_dir else ''
        jpeg = srcset_for(page_dir, src, suffix) if page_dir else ''
        if not webp:
            webp = src.rsplit('.', 1)[0] + '.webp'
        # sizes tells the browser how wide the image will render before it has
        # any layout to measure. Without it a srcset is guesswork and the
        # browser assumes the full viewport, which defeats the point.
        if jpeg and ' ' in jpeg:
            tag = tag[:-1].rstrip().rstrip('/').rstrip() + \
                  f' srcset="{jpeg}" sizes="{CONTENT_SIZES}">'
        return (f'<picture><source srcset="{webp}" sizes="{CONTENT_SIZES}" '
                f'type="image/webp">{tag}</picture>')

    return _IMG_RE.sub(wrap, markup)


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
        # dateModified is the review date when there is one. Repeating
        # datePublished here, as this did, tells Google the post has never been
        # touched — which is exactly the claim the freshness stamp exists to stop
        # the site making by accident.
        data['dateModified'] = post.get('reviewed') or post['iso']
    if post.get('tags'):
        data['keywords'] = ', '.join(post['tags'])
    # Google reads this for article rich results, and it is a separate field
    # from og:image. Setting one and not the other is the usual half-done job —
    # which is exactly what the guard here used to produce. cover_url is only ever populated for
    # newsletter editions, so all eight blog posts shipped a BlogPosting with no image at all while
    # og:image fell back to the site card for every one of them. Four editions got article rich
    # results and nine article pages were eligible only for a plain text listing.
    #
    # Same fallback as og:image, so the two cannot disagree again.
    data['image'] = SITE['base_url'] + (post.get('cover_url') or SITE['og_image'])
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
<!-- Delivered as a meta element because GitHub Pages cannot set response
     headers. Two consequences worth knowing: frame-ancestors is ignored in
     meta, so clickjacking is not mitigated here, and there is no way to set
     HSTS, COOP or X-Frame-Options at all. Those need a proxy in front.
     style-src keeps 'unsafe-inline' for the 55 style attributes in the
     markup; a CSS injection cannot execute script, and script-src carries
     no such escape hatch. cdnjs is allowed for one reason: Mermaid, fetched
     on demand and only for a page that has a diagram. -->
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; base-uri 'none'; object-src 'none'; frame-src 'none'; form-action 'none'; script-src 'self' https://cdnjs.cloudflare.com; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; manifest-src 'self'; require-trusted-types-for 'script'">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{site_title} — {title}</title>
<meta name="description" content="{description}">
<meta name="author" content="{author}">
<link rel="canonical" href="{canonical}">
<link rel="alternate" type="text/markdown" href="index.md" title="{title} (Markdown source)">
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
<link rel="preload" href="/vendor/fonts/inter-latin-wght-normal.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/vendor/fonts/jetbrains-mono-latin-wght-normal.woff2" as="font" type="font/woff2" crossorigin>
{code_theme}
<link rel="stylesheet" href="/css/styles.css">
<script type="application/ld+json">
{jsonld}
</script>
</head>
<body class="static-post">
<div id="read-progress"></div>
{nav}
<!-- The document's main landmark. Screen readers offer a jump-to-main
     command, and without one the only way past the navigation is to tab
     through it on every single page. One per document. -->
<main class="site-content" id="main">
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
          <div class="post-header-meta"><span id="post-date">{date}</span>{reviewed}<span id="post-readtime">{readtime}</span><span>{author}</span></div>
          {tags}
        </div>
{series}
{cover}
{origin}
{stale}
        <div class="post-content" id="post-content">
{content}
        </div>
        <div id="related-section">{related}</div>
      </article>
      <aside class="post-right-aside">
        <div class="post-aside-box">
          <div class="post-aside-title">// Share</div>
          <button class="share-btn" id="copy-link-btn" data-action="copy-link">⎘ Copy link</button>
          <a class="share-btn" href="https://x.com/intent/post?url={canonical_enc}&amp;text={title_enc}" target="_blank" rel="noopener">𝕏 Twitter / X</a>
          <a class="share-btn" href="https://www.linkedin.com/sharing/share-offsite/?url={canonical_enc}" target="_blank" rel="noopener">in LinkedIn</a>
          <button class="share-btn" id="copy-md-btn" type="button">⌄ Copy as Markdown</button>
        </div>
        <div class="post-aside-box">
          <div class="post-aside-title">// The JeffOps Dispatch</div>
          <p style="font-family:var(--mono);font-size:0.7rem;color:var(--text-dim);line-height:1.6;margin-bottom:0.75rem;">Every other Monday, published on LinkedIn.</p>
          <a class="share-btn" style="background:var(--cyan-glow);border-color:var(--border);color:var(--cyan);" href="/#newsletter">Subscribe →</a>
        </div>
        <div class="post-aside-box">
          <div class="post-aside-title">// Progress</div>
          <div class="progress-readout">
            <span id="scroll-pct">0%</span>
            <span id="scroll-remaining"></span>
          </div>
          <div style="height:3px;background:var(--bg3);margin-top:8px;border-radius:2px;">
            <div id="scroll-bar" style="height:100%;width:0%;background:var(--cyan);border-radius:2px;transition:width 0.1s;"></div>
          </div>
        </div>
      </aside>
    </div>
  </div>
</div>
</main>
{footer}
<!-- Deferred, so none of this blocks the first paint. Deferred scripts run
     in document order, which is the contract, and the order matters twice
     over: the sanitiser before the Trusted Types policy, and the policy before
     anything that writes to the DOM. highlight.js does — it replaces the
     contents of every code block — so it comes after, not before. -->
<script src="/vendor/purify.min.js" defer></script>
<script src="/js/trusted-types.js" defer></script>
{code_script}
<script src="/js/post-enhance.js" defer></script>
<script src="/js/post-page.js" defer></script>
</body>
</html>
"""


LIST_TEMPLATE = """<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="UTF-8">
<!-- Delivered as a meta element because GitHub Pages cannot set response
     headers. Two consequences worth knowing: frame-ancestors is ignored in
     meta, so clickjacking is not mitigated here, and there is no way to set
     HSTS, COOP or X-Frame-Options at all. Those need a proxy in front.
     style-src keeps 'unsafe-inline' for the 55 style attributes in the
     markup; a CSS injection cannot execute script, and script-src carries
     no such escape hatch. cdnjs is allowed for one reason: Mermaid, fetched
     on demand and only for a page that has a diagram. -->
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; base-uri 'none'; object-src 'none'; frame-src 'none'; form-action 'none'; script-src 'self' https://cdnjs.cloudflare.com; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; manifest-src 'self'; require-trusted-types-for 'script'">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{site_title} — Blog</title>
<meta name="description" content="{description}">
<link rel="canonical" href="{base_url}/posts/">
<meta property="og:type" content="website">
<meta property="og:url" content="{base_url}/posts/">
<meta property="og:title" content="{site_title} — Blog">
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
<link rel="preload" href="/vendor/fonts/inter-latin-wght-normal.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/vendor/fonts/jetbrains-mono-latin-wght-normal.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="/css/styles.css">
</head>
<body class="static-post">
{nav}
<!-- The document's main landmark. Screen readers offer a jump-to-main
     command, and without one the only way past the navigation is to tab
     through it on every single page. One per document. -->
<main class="site-content" id="main">
<div class="page active">
  <div class="section">
    <div class="section-header"><span class="section-tag">// writing</span><h1 class="section-title">Blog</h1><div class="section-line"></div></div>
    <div class="post-list">
{items}
    </div>
  </div>
</div>
</main>
{footer}
</body>
</html>
"""


# Syntax highlighting is 122KB of JavaScript and a stylesheet. Six of the ten
# pieces on this site contain no code block at all, and sending it to them is
# the same mistake as sending Mermaid to a page with no diagram — just smaller.
# Both are decided per page, from what the rendered HTML actually contains.
HIGHLIGHT_THEME = '<link rel="stylesheet" href="/vendor/github-dark.min.css">'
HIGHLIGHT_SCRIPT = '<script src="/vendor/highlight.min.js" defer></script>'

# Mermaid is 2.9MB — 875KB gzipped, more than everything else on the site put
# together — and it was being loaded by every post page, every edition and the
# home page, for zero diagrams. It is not vendored: carrying that in the
# repository for something nothing uses is worse than the request. The loader
# below fetches it from a CDN only once a diagram is genuinely on the page, so
# today it is never fetched at all.


def code_assets(content: str) -> tuple[str, str]:
    """(stylesheet, script) tags this page's content actually needs."""
    # '<pre><code', not '<code'. The looser test also matched the <code> a single inline backtick
    # produces, so a page whose only code was `like this` mid-sentence pulled in highlight.min.js
    # (121,727 B) and a render-blocking theme to highlight nothing — both consumers select
    # `pre code`. On the two pages affected that was 57% of their CSS and JS, and none of it is
    # recoverable by minify.py, which skips vendor/.
    # A regex, not a substring, and the substring version has now been wrong in both directions.
    # It began as `'<code' in content`, which also matched the <code> an inline backtick produces
    # and pulled the highlighter onto two pages with no code block at all. Tightening it to
    # '<pre><code' fixed that and then broke the moment reachable_code_blocks() started emitting
    # <pre tabindex="0" role="group" ...><code> for keyboard access — the literal stopped matching
    # anything, and every code block on the site rendered unhighlighted while the build, the
    # verifier and the smoke test all stayed green.
    #
    # Matching the tag rather than a byte sequence is what makes it survive the next attribute.
    has_code = re.search(r'<pre[^>]*><code', content) is not None
    has_diagram = 'language-mermaid' in content
    theme = HIGHLIGHT_THEME if has_code else ''
    script = HIGHLIGHT_SCRIPT if has_code else ''
    # Mermaid is not requested here at all: post-enhance.js loads it, from a
    # CDN, only once a diagram is on the page. has_diagram is still read so the
    # theme travels with a diagram-only page.
    if has_diagram and not theme:
        theme = HIGHLIGHT_THEME
    return theme, script


def build_post_page(post: dict, by_folder: dict, nav: str, footer: str,
                    by_series: dict | None = None, now: datetime | None = None,
                    out_dir: Path | None = None) -> str:
    content, toc = render_markdown(post['body_markdown'])
    content = size_images(content, out_dir) if out_dir else content
    content = offer_webp(content, set(post.get('webp_assets', [])), out_dir)
    reviewed_meta, stale_banner = freshness(post, now or utc_now())
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
        cover_name = post['cover_url'].rstrip('/').rsplit('/', 1)[-1]
        cover_img = (f'<img src="{html.escape(post["cover_url"], quote=True)}"'
                     f' alt="{html.escape(post.get("cover_alt", ""))}"{dims}>')
        if cover_name in set(post.get('webp_assets', [])):
            # Mirrors cover_url exactly, absolute or relative, so the two never
            # resolve against different bases. The narrow variants sit beside
            # it, so the srcset entries are just filenames swapped in.
            base = post['cover_url'].rsplit('.', 1)[0]
            suffix = '.' + post['cover_url'].rsplit('.', 1)[1]
            narrow_webp = out_dir and (out_dir / f'{cover_name.rsplit(".",1)[0]}-{NARROW_WIDTH}.webp').is_file()
            narrow_jpeg = out_dir and (out_dir / f'{cover_name.rsplit(".",1)[0]}-{NARROW_WIDTH}{suffix}').is_file()
            webp_set = (f'{base}-{NARROW_WIDTH}.webp {NARROW_WIDTH}w, '
                        f'{base}.webp {post.get("cover_width", 1200)}w') if narrow_webp \
                       else f'{base}.webp'
            if narrow_jpeg:
                cover_img = cover_img[:-1].rstrip() + (
                    f' srcset="{base}-{NARROW_WIDTH}{suffix} {NARROW_WIDTH}w, '
                    f'{post["cover_url"]} {post.get("cover_width", 1200)}w"'
                    f' sizes="{CONTENT_SIZES}">')
            cover_img = (f'<picture><source srcset="{html.escape(webp_set, quote=True)}"'
                         f' sizes="{CONTENT_SIZES}" type="image/webp">{cover_img}</picture>')
        cover_html = f'        <figure class="post-cover">{cover_img}</figure>'

    theme_tag, script_tag = code_assets(content)
    return POST_TEMPLATE.format(
        code_theme=theme_tag,
        code_script=script_tag,
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
        reviewed=reviewed_meta,
        stale=stale_banner,
        series=series_nav(post, by_series or {}),
        readtime=post['readtime'],
        tags=tags_html,
        content=content,
        related=related_html(post, by_folder),
    )


def render_post_items(posts: list[dict], compact: bool = False) -> list[str]:
    """One <div class="post-item"> per post.

    Shared by /posts/ and by the home page's list, which used to ship
    <div class="post-item">Loading posts...</div> and let JavaScript fill it in. That left the home
    page with zero crawlable links to any post, on the page holding every internal link the site
    has — while the newsletter archive one section over emitted real anchors for all five editions
    and proved the correct shape. Rendering both from here means the two lists cannot drift into
    disagreeing about what a post looks like.
    """
    items = []
    for post in posts:
        chips = ''.join(f'<span class="tag">{html.escape(t)}</span>' for t in post.get('tags', []))
        chips_html = (f'<div style="display:flex;flex-wrap:wrap;gap:6px;margin:8px 0;">{chips}</div>'
                      if chips else '')
        # compact carries the links and nothing else. The home page's copy exists so a crawler can
        # reach every post from the page holding the site's authority; it is not a second reading of
        # the blog index, and rendering the excerpts there made the home page duplicate 86% of
        # /posts/ by body text for prose nobody reads twice. js/app.js clears #post-list and
        # re-renders from blog/index.json on load, so a visitor with scripts sees the full list
        # either way — only crawlers and no-JS readers ever see what is written here.
        excerpt_html = '' if compact else (
            f'          <div class="post-excerpt">{html.escape(post.get("excerpt", ""))}</div>\n'
            f'          {chips_html}\n')
        items.append(
            f'      <div class="post-item">\n'
            f'        <div>\n'
            f'          <a class="post-title" href="{post["url"]}">{html.escape(post["title"])}</a>\n'
            f'{excerpt_html}'
            f'          <div class="post-meta"><span>{post["date"]}</span><span>{post["readtime"]}</span></div>\n'
            f'        </div>\n'
            f'        <div class="post-read-time">→</div>\n'
            f'      </div>'
        )
    return items


POST_LIST_RE = re.compile(
    r'(<div class="post-list" id="post-list">).*?(</div>\s*</div>)', re.DOTALL)


def inject_posts(index_html: str, posts: list[dict]) -> str:
    """Put the real post list into index.html, the way inject_editions does for the archive."""
    markup = '\n'.join(render_post_items(posts, compact=True))
    result, count = POST_LIST_RE.subn(
        lambda m: f'{m.group(1)}\n{markup}\n        {m.group(2)}', index_html, count=1)
    if not count:
        raise SystemExit('Could not find <div class="post-list" id="post-list"> in index.html '
                         '- the home page post list cannot be generated.')
    return result


def build_list_page(posts: list[dict], nav: str, footer: str) -> str:
    items = render_post_items(posts)
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
<!-- Delivered as a meta element because GitHub Pages cannot set response
     headers. Two consequences worth knowing: frame-ancestors is ignored in
     meta, so clickjacking is not mitigated here, and there is no way to set
     HSTS, COOP or X-Frame-Options at all. Those need a proxy in front.
     style-src keeps 'unsafe-inline' for the 55 style attributes in the
     markup; a CSS injection cannot execute script, and script-src carries
     no such escape hatch. cdnjs is allowed for one reason: Mermaid, fetched
     on demand and only for a page that has a diagram. -->
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; base-uri 'none'; object-src 'none'; frame-src 'none'; form-action 'none'; script-src 'self' https://cdnjs.cloudflare.com; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; manifest-src 'self'; require-trusted-types-for 'script'">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{site_title} — {title}</title>
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
<link rel="preload" href="/vendor/fonts/inter-latin-wght-normal.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/vendor/fonts/jetbrains-mono-latin-wght-normal.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="/css/styles.css">
</head>
<body class="static-post">
{nav}
<!-- The document's main landmark. Screen readers offer a jump-to-main
     command, and without one the only way past the navigation is to tab
     through it on every single page. One per document. -->
<main class="site-content" id="main">
<div class="page active">
  <div class="post-page-wrap">
    <div style="max-width:{measure};margin:0 auto;padding-top:2rem;"><a class="back-btn" href="/">← Back to JeffOps</a></div>
    <article style="max-width:{measure};margin:0 auto;">
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
</main>
{footer}
<!-- These pages are lifted out of the app and load none of it, so the enquiry
     forms they carry had no handlers: the Send button did nothing and threw
     nothing, and what someone typed went nowhere. This is the one script they
     need — and, since 2026-08-31, the only one.

     purify.min.js and trusted-types.js used to be here too, directly above a
     comment calling forms.js "the one script they need". forms.js has no sink:
     no innerHTML, no insertAdjacentHTML, no document.write, no new Function. It
     touches .value, .textContent, .style.display and location.href. So the
     default policy was installed on /about, /consulting, /training, /speaking
     and /security-policy and never once invoked — 10,706 bytes gzipped of
     purify alone, and under vendor/ so minify.py never shrinks it, on the five
     pages a prospective client lands on.

     Dropping it fails CLOSED rather than opening a hole: these pages still send
     require-trusted-types-for 'script', so if a sink ever appears here it
     throws instead of running unsanitised. The sanitiser has to come back with
     the sink, not before it. -->
<script src="/js/forms.js" defer></script>
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
            measure='760px',
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
            '<div class="talk-event">'
            f'<span class="talk-event-head">{html.escape(str(talk.get("event", "")))}{badge}</span>'
            f'<div class="talk-links">{links}</div>'
            '</div>'
            f'<div class="talk-title">{html.escape(str(talk.get("title", "")))}</div>'
            f'<div class="talk-location">📍 {html.escape(str(talk.get("location", "")))}</div>'
            '</div></div>')
    return ''.join(items)


def render_topic_options(content: str) -> str:
    """Fill the speaking enquiry dropdown at build time.

    A promoted page loads no JavaScript, so the topic list — fetched by the app
    on the single-page view — never arrived here. The static /speaking/ page,
    which is what a crawler and a visitor without scripting see, offered a
    dropdown containing only '— Select —'. Rendering the options from
    speaking_topics.json fixes that and keeps one list rather than two: the app
    now leaves options already in the page alone.
    """
    source = ROOT / 'speaking_topics.json'
    if not source.exists() or 'id="eq-topic"' not in content:
        return content
    try:
        topics = json.loads(source.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        print(f'  ! speaking_topics.json unreadable ({exc}); dropdown left empty')
        return content
    options = ''.join(
        f'<option value="{html.escape(str(t["value"]), quote=True)}">'
        f'{html.escape(str(t["label"]))}</option>'
        for t in topics if t.get('value') and t.get('label'))
    return content.replace('<option value="">— Select —</option>',
                           f'<option value="">— Select —</option>{options}', 1)


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
        content = render_topic_options(content)
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
            measure='1200px',
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


def _absolutise_feed_images(body: str, post: dict) -> str:
    """Make every image in a feed body absolute.

    A post writes ![alt](01-record-types.jpg), which is correct beside its own index.html and wrong
    everywhere else. There is no xml:base here, so a reader resolves that against the feed document
    itself — https://jeffops.com/rss.xml — and asks for https://jeffops.com/01-record-types.jpg,
    which 404s. All 17 images in the feed were doing this. Readers that rebase against the item
    <link> happen to survive; strict consumers and RSS-to-email, which is what a Dispatch gets
    plugged into, do not.

    Scoped to img src on purpose: every <a href> in the same bodies is already absolute, because
    render_markdown is given absolute link targets and only image paths stay relative.
    """
    prefix = SITE['base_url'] + post['url']
    return re.sub(r'(<img\b[^>]*?\bsrc=")(?!https?://|//|/|data:)',
                  lambda m: m.group(1) + prefix, body)


def build_rss(posts: list[dict]) -> str:
    items = []
    for post in posts:
        body, _ = render_markdown(post['body_markdown'])
        body = _absolutise_feed_images(body, post)
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


def _today_iso() -> str:
    """Today in the site's own timezone.

    A post dated the 17th should appear on the 17th where it was written, not wherever the runner
    happens to be. The daily build is the publishing mechanism, so this is the line that decides
    whether an edition is out yet.
    """
    return in_site_tz(utc_now()).date().isoformat()


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

    editions, withheld = [], []
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
            'is_published': False,
            'tags': front.get('tags') or ['Newsletter'],
            'readtime': estimate_readtime(body) if has_body else '',
            'body_markdown': strip_leading_h1(body).strip() if has_body else '',
            'markdown': body if has_body else '',
            'description': front.get('description', '').strip()
                           or (parse_excerpt(body) if has_body else ''),
        }
        edition['excerpt'] = edition['description']
        attach_cover(edition, front, source)

        # An edition obeys the same two gates a post does. is_published was hardcoded True here, so
        # `draft: true` on an edition did nothing at all and a future date published immediately —
        # into the page, both feeds, the sitemap and the home-page archive. The feed carries the
        # full body, so a subscriber pull cannot be recalled; of everything on this site that could
        # go wrong, an embargo breaking is the one that cannot be taken back.
        #
        # The identical mistake on a blog post has always been caught. Editions were simply never
        # run past the same gate.
        if is_draft(front):
            withheld.append((edition['title'], 'draft'))
            continue
        if date_iso and date_iso > _today_iso():
            withheld.append((edition['title'], f'dated {date_iso}'))
            continue

        edition['is_published'] = True
        editions.append(edition)

    for title, why in withheld:
        print(f'  · withheld ({why}): {title[:56]}')

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


def build_edition_pages(out: Path, editions: list[dict], nav: str, footer: str,
                        by_series: dict | None = None, now: datetime | None = None) -> list[dict]:
    """Render every edition that has a body. Returns the ones rendered."""
    published = [e for e in editions if e['has_body']]
    for edition in published:
        page_dir = out / edition['url'].strip('/')
        page_dir.mkdir(parents=True, exist_ok=True)

        # The cover sits next to the page it belongs to, the way a post's
        # assets do, so the URL in the markup and the file on disk cannot
        # drift apart. Everything in the edition's folder except the markdown
        # is an asset it references, so a relative src in the body resolves
        # too, not only the declared cover. Copied before the page is rendered,
        # because the renderer needs to know which of them gained a WebP.
        folder = ROOT / 'newsletter' / edition['folder_name']
        if folder.is_dir():
            for asset in sorted(folder.iterdir()):
                if asset.is_file() and asset.suffix.lower() not in ('.md', '.markdown'):
                    shutil.copy2(asset, page_dir / asset.name)
                    if write_webp(page_dir / asset.name, narrow=True):
                        edition.setdefault('webp_assets', []).append(asset.name)

        page = build_post_page(edition, {}, nav, footer, by_series, now, page_dir)
        (page_dir / 'index.html').write_text(page, encoding='utf-8')
        write_markdown_source(page_dir, edition)
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


# The site is open to every crawler: search engines, AI training crawlers, AI
# retrieval agents, aggregators, all of it. This used to split AI bots into
# three groups and decline the training ones. It no longer does.
#
# Jeff's choice, 6 August 2026: allow everything. The writing is here to be
# read, indexed, quoted, cited and learned from, and every named exception was
# a place where a crawler could be turned away for no return. One wildcard rule
# says that without ambiguity, and there is no per-bot list to keep current as
# crawler tokens are renamed, split or retired.
#
# Deliberately kept out of this file:
#   - No Disallow lines at all. A single wrong token removes the site from a
#     search engine, and an empty exception list cannot go wrong that way.
#   - No Crawl-delay. Google ignores it, and the site is static and cheap.
#
# Drafts stay out of indexes through a per-page noindex meta tag rather than a
# path rule here, which is the right layer for it: robots.txt only asks a
# crawler not to fetch, while noindex asks it not to list what it fetched.
#
# None of this is enforcement. robots.txt is a request, honoured voluntarily,
# and a crawler that ignores it faces nothing here. It states the policy; it
# does not implement it.


def build_robots() -> str:
    # One group, no exceptions. Every comment sits on its own line, never
    # trailing a directive: RFC 9309 does allow an inline '#' and says the value
    # ends there, but not every crawler implements that, and a naive parser that
    # reads the rest of the line as the token matches nothing and silently
    # applies no rule at all.
    return f"""# robots.txt for {SITE['base_url']}
#
# Everything is welcome here.
#
# Search engines, AI training crawlers, AI retrieval agents answering someone's
# question right now, aggregators — all of them, on all of it. Nothing is
# disallowed, and no crawler is named as an exception, because there are none.
#
# Unpublished drafts carry a noindex meta tag on the page itself rather than a
# rule here. That is the correct layer: this file asks a crawler not to fetch,
# noindex asks it not to list.
#
# This file is a request. Crawlers honour it voluntarily.

User-agent: *
Allow: /

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

    # The logo mark, pre-rasterised and committed rather than converted from SVG
    # at build time. Pillow cannot read SVG, and adding cairosvg would put a
    # native-library dependency into CI to redraw the same 260px image on every
    # run. The wordmark is deliberately not used here: it is dark navy, which
    # sits at 2:1 against this background, and the card already says JeffOps.com
    # in type. The mark is gradient teal and reads cleanly.
    mark_path = ROOT / 'og-mark.png'
    if mark_path.exists():
        mark = Image.open(mark_path).convert('RGBA')
        img.paste(mark, (W - mark.width - 80, 80), mark)
    else:
        print('  ! og-mark.png not found; the share card will have no logo')

    draw.text((80, 200), 'JeffOps.com', font=font(86), fill='#e8edf2')
    draw.text((80, 310), SITE['tagline'], font=font(44), fill='#00D9FF')
    draw.text((80, 400), 'Practical AI-tomation, platform engineering', font=font(30, False), fill='#9baab8')
    draw.text((80, 444), 'and enterprise ops, from inside the environment.', font=font(30, False), fill='#9baab8')
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
    # they join the feed and the sitemap. They do not join the blog index. A
    # newsletter edition is not a blog post, and the two archives stay separate:
    # /posts/ and the blog list in the single-page app both read the blog index,
    # while /#newsletter reads the archive injected into index.html. Each list
    # holds one kind of thing. Editions that have not been copied across are
    # still only on LinkedIn and appear nowhere but that archive, pointing
    # there. One list, filtered once, so no consumer can disagree about which
    # editions exist here.
    editions = load_editions()
    on_site_editions = [e for e in editions if e['has_body']]
    writing = sorted(live + on_site_editions,
                     key=lambda item: item.get('iso', ''), reverse=True)

    # The client-side index is always written from the live set, even in preview.
    # It is a committed file, so letting a scheduled post into it would put the
    # full text of an unpublished piece into the repository's own output.
    # Heading ids come from the markdown renderer here, and the single-page app
    # reads them back out of the index rather than inventing its own scheme.
    # Two views of one post must not produce two different #fragment URLs — a
    # link someone copied from the SPA has to land on the static page too.
    for item in live:
        item['headings'] = render_markdown(item.get('body_markdown') or '')[1]

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
    nav, footer = extract_shell(
        current_year((ROOT / 'index.html').read_text(encoding='utf-8'), now))

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

    # Series membership is a property of the whole set, not of one post, so it
    # is worked out once here and handed to every page.
    by_series = group_series(posts + on_site_editions)

    print(f'Rendering {len(posts)} post pages…')
    for post in posts:
        page_dir = out / post['url'].strip('/')
        page_dir.mkdir(parents=True, exist_ok=True)

        # Assets are copied and their WebP variants written before the page is
        # rendered, not after: the renderer has to know which images have a
        # WebP sibling before it can offer one.
        source_dir = ROOT / post['folder']
        if source_dir.is_dir():
            for asset in sorted(source_dir.iterdir()):
                if asset.is_file() and asset.suffix.lower() not in ('.md', '.markdown'):
                    shutil.copy2(asset, page_dir / asset.name)
                    if write_webp(page_dir / asset.name, narrow=True):
                        post.setdefault('webp_assets', []).append(asset.name)

        page = build_post_page(post, by_folder, nav, footer, by_series, now, page_dir)
        write_markdown_source(page_dir, post)
        if not post.get('is_published', True):
            when = post['published_at'][:16].replace('T', ' ') + ' UTC'
            page = page.replace('<head>',
                                '<head>\n<meta name="robots" content="noindex,nofollow">', 1)
            page = page.replace('<div class="post-content" id="post-content">',
                                '<div class="post-content" id="post-content">\n'
                                + PREVIEW_BANNER.format(when=when), 1)
        (page_dir / 'index.html').write_text(page, encoding='utf-8')
        print(f'  → {post["url"]}' + ('   [preview, not live]'
                                      if not post.get('is_published', True) else ''))

    rendered = build_edition_pages(out, editions, nav, footer, by_series, now)
    for edition in rendered:
        print(f'  → {edition["url"]}')

    # The client-side index is written here rather than earlier, because it now
    # carries which assets gained a WebP sibling — and that is only known once
    # the pages have been rendered and their images written out. copy_blog then
    # publishes the freshly written files.
    write_index_files(live)
    copy_blog(out, live)
    waiting = [e for e in editions if not e['has_body']]
    if waiting:
        print(f'{len(waiting)} edition(s) not copied across yet, still linking to LinkedIn:')
        for edition in waiting:
            print(f'  · #{edition["number"]} {edition["title"]}  ({edition["source"]})')

    index_source = current_year(
        (ROOT / 'index.html').read_text(encoding='utf-8'), now)

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
    index_source = inject_posts(index_source, live)

    problems: list[str] = []
    cells, declared = build_stat_cells(live, talks, editions, problems.append)
    for problem in problems:
        print(f'  ! {problem}')
    index_source = inject_stats(index_source, cells)
    index_source = inject_events(index_source)
    index_source = inject_counts(index_source, live, talks)
    index_source = inject_home_meta(index_source, live)
    index_source = rotate_portrait(index_source, now, out)
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
