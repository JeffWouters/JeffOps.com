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

from generate_blog_index import (ROOT, collect_posts, parse_frontmatter, parse_title,
                                 strip_leading_h1, unpublished_posts, utc_now,
                                 write_index_files)

# ── Site configuration ────────────────────────────────────────────────
SITE = {
    'base_url': 'https://jeffops.com',
    'title': 'JeffOps',
    'tagline': 'Tech. Ops. Dev.',
    'description': 'Practical AI-tomation, platform engineering and enterprise '
                   'ops from Jeff Wouters. Written from inside a 25,000-user '
                   'environment, not from a vendor deck.',
    'author': 'Jeff Wouters',
    'email': 'jeff@jeffops.com',
    'language': 'en',
    'og_image': '/og-card.png',
}

# Files and folders copied verbatim into the output.
STATIC_ASSETS = ['index.html', 'css', 'js', 'speaking_talks.json',
                 'speaking_topics.json', 'newsletter_editions.json',
                 'JeffOps_Speaking.jpg']

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
<meta property="og:image" content="{base_url}{og_image}">
<meta property="og:site_name" content="{site_title}">
<meta property="article:author" content="{author}">
{article_meta}
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{description}">
<meta name="twitter:image" content="{base_url}{og_image}">
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
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=JetBrains+Mono:wght@400;700&family=Syne:wght@700;800&display=swap" rel="stylesheet">
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
    <div style="padding-top:2rem;"><a class="back-btn" href="/#blog">← Back to Blog</a></div>
    <div class="post-page-layout">
      <aside class="post-toc-aside">
        <div class="toc-label">Contents</div>
        <div id="toc-links">{toc}</div>
      </aside>
      <article>
        <div class="post-header">
          <div class="post-header-type">// Blog Post</div>
          <h1 id="post-title">{title}</h1>
          <div class="post-header-meta"><span id="post-date">{date}</span><span id="post-readtime">{readtime}</span><span>{author}</span></div>
          {tags}
        </div>
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
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=JetBrains+Mono:wght@400;700&family=Syne:wght@700;800&display=swap" rel="stylesheet">
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
        article_meta=article_meta,
        jsonld=json_ld(post),
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
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=JetBrains+Mono:wght@400;700&family=Syne:wght@700;800&display=swap" rel="stylesheet">
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
      <div class="post-content">
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
def load_editions() -> list[dict]:
    path = ROOT / 'newsletter_editions.json'
    if not path.exists():
        print('  ! newsletter_editions.json not found — archive will be empty')
        return []
    editions = json.loads(path.read_text(encoding='utf-8'))
    editions.sort(key=lambda e: e.get('date', ''), reverse=True)
    return editions


def render_editions(editions: list[dict]) -> str:
    """Build the archive list markup.

    Rendered here rather than fetched by the browser for the same reason posts
    are: these are outbound links to published work, and a link that only exists
    after JavaScript runs is a link most crawlers never see.
    """
    if not editions:
        return '      <!-- No editions in newsletter_editions.json. -->'

    rows = []
    for edition in editions:
        try:
            published = datetime.fromisoformat(edition['date'])
            shown = published.strftime('%b %d, %Y')
            iso = edition['date']
        except (KeyError, ValueError):
            shown, iso = edition.get('date', ''), ''
        number = f'#{int(edition["number"]):03d}' if str(edition.get('number', '')).isdigit() else ''
        rows.append(
            f'      <a class="issue-item" style="text-decoration:none;color:inherit;" '
            f'href="{html.escape(edition["url"], quote=True)}" target="_blank" rel="noopener">'
            f'<div class="issue-num">{number}</div>'
            f'<div><div class="issue-title">{html.escape(edition["title"])}</div>'
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


def build_robots() -> str:
    return f"""User-agent: *
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
    draw.text((80, 200), 'JeffOps.com', font=font(86), fill='#e8edf2')
    draw.text((80, 310), 'Tech. Ops. Dev.', font=font(44), fill='#00D9FF')
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

    # The client-side index is always written from the live set, even in preview.
    # It is a committed file, so letting a scheduled post into it would put the
    # full text of an unpublished piece into the repository's own output.
    posts = write_index_files(live)
    live_urls = {p['url'] for p in posts}
    if args.preview:
        extra = [p for p in collect_posts(include_unpublished=True, now=now)
                 if p['url'] not in live_urls]
        posts = posts + extra
    if pending:
        print(f'{len(pending)} post(s) not published yet:')
        report_schedule(pending)

    # A duplicate URL means two posts would overwrite each other — fail loudly
    # rather than silently publishing one of them.
    seen: dict[str, str] = {}
    for post in posts:
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

    editions = load_editions()
    index_source = (ROOT / 'index.html').read_text(encoding='utf-8')
    (out / 'index.html').write_text(inject_editions(index_source, editions), encoding='utf-8')
    print(f'Injected {len(editions)} newsletter edition(s) into index.html')

    page_urls = build_standalone_pages(out, nav, footer)
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
    feed = build_rss(live)
    (out / 'rss.xml').write_text(feed, encoding='utf-8')
    # Hugo published the feed at /index.xml for years. Anyone still subscribed
    # points there, and a feed reader that meets a redirect may simply drop the
    # subscription, so the same bytes are served at the old path too.
    (out / 'index.xml').write_text(feed, encoding='utf-8')
    (out / 'sitemap.xml').write_text(build_sitemap(live, page_urls), encoding='utf-8')
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
