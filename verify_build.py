#!/usr/bin/env python3
"""Verify a build before it ships.

The failure this guards against is specific and quiet: a build that produces
pages successfully but produces *empty* pages — content that lives only in JSON
and never reaches the HTML. That looks fine to a human clicking around with
JavaScript enabled and is invisible to everything else. So the central check
here is that the article text is present as literal text in the response body.

Exits non-zero on failure so CI refuses to deploy.

Usage:  python verify_build.py [_site]
"""

from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

from generate_blog_index import ROOT, collect_posts, unpublished_posts


class TextExtractor(HTMLParser):
    """Strip tags so we test what a reader actually sees, not the markup."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ('script', 'style') and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)

    def text(self) -> str:
        return re.sub(r'\s+', ' ', ''.join(self.parts))


def visible_text(html_source: str) -> str:
    parser = TextExtractor()
    parser.feed(html_source)
    return parser.text()


# Lines that are not plain prose. Each becomes its own element in the rendered
# HTML, so a probe must never span one.
NON_PROSE = re.compile(r'^\s*(#{1,6}\s|[-*+]\s|\d+[.)]\s|>\s?|\||```|<|!\[|\s*$)')


def _inline_text(line: str) -> str:
    """Reduce a markdown line to the text a reader would see.

    Order matters. Links are unwrapped before inline code, because link text
    frequently contains code spans, and stripping the backticks first leaves a
    mangled link that no longer matches. Inline code keeps its contents rather
    than being blanked, since the rendered page shows that text too.
    """
    line = re.sub(r'!?\[([^\]]*)\]\([^)]*\)', r'\1', line)    # links and images
    line = re.sub(r'`([^`]*)`', r'\1', line)                  # inline code, kept
    line = re.sub(r'\*\*(.+?)\*\*', r'\1', line)              # bold
    line = re.sub(r'(?<!\w)\*(.+?)\*(?!\w)', r'\1', line)     # italic
    return re.sub(r'\s+', ' ', line).strip()


def probes(markdown_body: str) -> list[str]:
    """Distinctive prose fragments from a post, for presence testing.

    Probes come from runs of consecutive plain-prose lines — one such run is one
    <p> in the output, so a slice of it survives rendering intact. Splitting on
    sentences instead would silently weld a heading onto the paragraph below it
    and produce a string that appears nowhere, failing a page that is fine.
    """
    body = re.sub(r'```.*?```', '\n\n', markdown_body, flags=re.DOTALL)  # fenced code
    # HTML comments survive into the output as comments, so their text is never
    # visible. Their continuation lines look exactly like prose to the line
    # scanner below, which would then fail the page for "missing" text that was
    # never meant to render.
    body = re.sub(r'<!--.*?-->', '\n\n', body, flags=re.DOTALL)
    found: list[str] = []
    paragraph: list[str] = []

    def flush() -> None:
        if not paragraph:
            return
        text = _inline_text(' '.join(paragraph))
        if len(text) > 60:
            found.append(text[:100])
        paragraph.clear()

    for line in body.splitlines():
        if NON_PROSE.match(line):
            flush()
        else:
            paragraph.append(line)
    flush()
    return found


# RFC 9116 Section 2.5. Anything else is an extension field, which the spec
# permits but which no consumer understands, so it is almost always a typo.
SECURITY_FIELDS = {
    'acknowledgments', 'canonical', 'contact', 'encryption',
    'expires', 'hiring', 'policy', 'preferred-languages',
}
SINGLETON_FIELDS = {'expires', 'preferred-languages'}

# The near-misses worth naming explicitly rather than reporting as "unknown
# field". The first is the single most common error in the wild: roughly one in
# eight real files spells it the British way, and the field then does nothing.
SECURITY_TYPOS = {
    'acknowledgements': 'Acknowledgments',
    'acknowledgement': 'Acknowledgments',
    'acknowledgment': 'Acknowledgments',
    'contacts': 'Contact',
    'expire': 'Expires',
    'expiry': 'Expires',
    'preferred-language': 'Preferred-Languages',
    'preferredlanguages': 'Preferred-Languages',
}

# How close to the Expires date the build is still willing to publish. An
# expired security.txt is worse than none at all — RFC 9116 tells researchers
# not to trust one — and the failure is silent, because nothing about the file
# changes on the day it dies. Failing early turns a silent expiry into a build
# error at the next push, while there is still a month to act on it.
SECURITY_RENEW_DAYS = 30


def check_security_txt(out: Path, fail) -> None:
    """Validate security.txt against RFC 9116, strictly.

    Both served copies are checked, because the point of the legacy root copy
    is to survive a deploy that strips dotfiles, and a copy that has drifted
    from the real one would then publish stale contact details on its own.
    """
    required = out / '.well-known' / 'security.txt'
    legacy = out / 'security.txt'

    if not required.exists():
        fail('/.well-known/security.txt is missing — RFC 9116 requires that exact path')
        return

    raw = required.read_bytes()
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError as exc:
        fail(f'security.txt is not valid UTF-8: {exc}')
        return

    if legacy.exists():
        if legacy.read_bytes() != raw:
            fail('security.txt differs between /.well-known/ and the root — '
                 'the two copies have drifted, so one of them is publishing stale details')
    else:
        fail('the legacy root copy of security.txt was not written')

    fields: dict[str, list[str]] = {}
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip() or line.startswith('#'):
            continue
        if ':' not in line:
            fail(f'security.txt line {number} is neither blank, a comment, nor a field: {line!r}')
            continue
        name, _, value = line.partition(':')
        key = name.strip().lower()
        # The grammar is "field-name ':' SP value" — exactly one space, and no
        # leading whitespace on the line. Parsers that follow it literally drop
        # anything else, which is why roughly a third of real files fail here.
        if name != name.strip() or not value.startswith(' ') or value.startswith('  '):
            fail(f'security.txt line {number} does not match the RFC 9116 grammar '
                 f'(expected "Field: value" with exactly one space): {line!r}')
        fields.setdefault(key, []).append(value.strip())

    for key in fields:
        if key in SECURITY_TYPOS:
            fail(f'security.txt uses "{key}" — RFC 9116 spells it '
                 f'"{SECURITY_TYPOS[key]}", and consumers ignore anything else')
        elif key not in SECURITY_FIELDS:
            fail(f'security.txt has an unrecognised field "{key}"')

    for key in SINGLETON_FIELDS:
        if len(fields.get(key, [])) > 1:
            fail(f'security.txt has {len(fields[key])} "{key}" fields — the RFC allows one')

    # Contact: required, and the ordering is meaningful, so the first one is the
    # address that will actually be used.
    contacts = fields.get('contact', [])
    if not contacts:
        fail('security.txt has no Contact field, which RFC 9116 requires')
    for value in contacts:
        if not re.match(r'^(mailto:|tel:|https://)', value):
            fail(f'Contact "{value}" is not a URI — RFC 9116 requires a scheme, '
                 f'so an email address must be written as mailto:…')
        if value.startswith('mailto:') and '@' not in value:
            fail(f'Contact "{value}" has no address in it')

    # Every other field that carries a URI must be https, without exception.
    for key in ('encryption', 'policy', 'acknowledgments', 'canonical', 'hiring'):
        for value in fields.get(key, []):
            if not value.startswith('https://'):
                fail(f'{key} "{value}" must use https')
    for value in fields.get('encryption', []):
        if 'BEGIN PGP' in value:
            fail('Encryption must be a URI pointing at a key, never the key itself')

    # Canonical must cover both served paths, or the copy at the uncovered path
    # is one a researcher is told not to trust.
    canonicals = set(fields.get('canonical', []))
    if canonicals:
        for expected in ('https://jeffops.com/.well-known/security.txt',
                         'https://jeffops.com/security.txt'):
            if expected not in canonicals:
                fail(f'security.txt is served at {expected} but does not list it as Canonical, '
                     f'so RFC 9116 says its contents should not be trusted there')

    # A Policy or Acknowledgments link into our own site that 404s is worse than
    # no link, and it is invisible until someone follows it.
    for key in ('policy', 'acknowledgments'):
        for value in fields.get(key, []):
            path = re.sub(r'^https://jeffops\.com', '', value.split('#')[0])
            if path == value:
                continue
            if not (out / path.strip('/') / 'index.html').exists():
                fail(f'{key} points at {value}, which this build does not produce')

    # Expires: present, parseable, in the future, under a year out, and not
    # about to lapse.
    expires = fields.get('expires', [])
    if not expires:
        fail('security.txt has no Expires field, which RFC 9116 requires')
        return
    try:
        when = datetime.fromisoformat(expires[0].replace('Z', '+00:00').replace('z', '+00:00'))
    except ValueError:
        fail(f'Expires "{expires[0]}" is not an RFC 3339 timestamp')
        return
    if when.tzinfo is None:
        fail(f'Expires "{expires[0]}" has no timezone offset')
        return

    now = datetime.now(timezone.utc)
    days = (when - now).days
    if days < 0:
        fail(f'security.txt expired {abs(days)} day(s) ago — RFC 9116 tells researchers '
             f'not to trust an expired file, so this is worse than not having one')
    elif days < SECURITY_RENEW_DAYS:
        fail(f'security.txt expires in {days} day(s). Review the contact details and '
             f'push a new Expires date before this ships.')
    elif days > 366:
        fail(f'Expires is {days} days out; RFC 9116 recommends less than a year '
             f'so that the file means something')



def check_schedule(out: Path, fail) -> None:
    """Nothing unpublished may appear anywhere in the output.

    Gating the page render is the easy half. The half that actually leaks is
    everything else that iterates posts: the client index, the feed, the
    sitemap, and the wholesale copy of the blog directory that used to serve
    every post.md verbatim. So this does not check the rule was applied, it
    checks the result, by searching the built output for each withheld post's
    URL, slug and folder path.

    It also refuses a preview build. A preview renders scheduled posts on
    purpose, which is exactly what must never reach production, so the marker it
    leaves behind is a hard failure rather than a warning.
    """
    marked = [f for f in out.rglob('*.html')
              if 'data-preview-build="1"' in f.read_text(encoding='utf-8', errors='ignore')]
    if marked:
        fail(f'this is a preview build ({len(marked)} page(s) carry the preview banner) '
             f'and must not be deployed. Rebuild without --preview.')

    # Anything in the output that no published post accounts for. On a fresh CI
    # runner this is always empty, because the output directory does not exist
    # yet. On a workstation the wipe can be refused — a file held open, a synced
    # folder, a mount that will not allow deletes — and the build says so and
    # carries on. What it leaves behind is a directory of retired drafts and
    # renamed posts that still serve perfectly well over HTTP. Scheduling is
    # worth nothing if last month's withdrawn draft is still sitting there.
    posts_now = collect_posts()
    live = {p['url'].strip('/') for p in posts_now}
    live_folders = {p['folder'] for p in posts_now}

    # A redirect stub sits at a URL no current post produces, which is the whole
    # point of it. Exempt the ones we declared, and only those, so a genuinely
    # stale page is still caught.
    redirects_file = ROOT / 'redirects.json'
    if redirects_file.exists():
        import json as _json
        live |= {p.strip('/') for p in _json.loads(redirects_file.read_text(encoding='utf-8'))}

    for page in sorted(out.glob('posts/*/*/index.html')):
        rel = page.parent.relative_to(out).as_posix()
        if rel not in live:
            fail(f'{rel}/ is in the output but no current post produces it — '
                 f'stale page from an earlier build, and it is being served')

    for folder in sorted(p for p in out.glob('blog/*/*') if p.is_dir()):
        rel = folder.relative_to(out).as_posix()
        if rel not in live_folders:
            fail(f'{rel}/ is in the output but is not a published post — '
                 f'stale source markdown from an earlier build')

    pending = unpublished_posts()
    if not pending:
        return

    searchable = {}
    for path in out.rglob('*'):
        if path.is_file() and path.suffix in ('.html', '.xml', '.json', '.js', '.txt', '.md'):
            searchable[path] = path.read_text(encoding='utf-8', errors='ignore')

    for post in pending:
        label = post['title'][:50]
        when = post['date'] or post['published_at'][:10]

        page = out / post['url'].strip('/') / 'index.html'
        if page.exists():
            fail(f'"{label}" is not published until {when} but its page was generated '
                 f'at {post["url"]}')

        folder = out / post['folder']
        if folder.exists():
            fail(f'"{label}" is not published until {when} but its source markdown was '
                 f'copied to {post["folder"]}, where anyone can read it')

        for path, text in searchable.items():
            if post['url'] in text:
                rel = path.relative_to(out)
                fail(f'"{label}" is not published until {when} but its URL appears in {rel}')
                break

        # The client index embeds the full body, so a leak there is the whole
        # article rather than a link to it.
        probe = re.sub(r'\s+', ' ', post['body_markdown'])[:120].strip()
        if len(probe) > 60:
            for name in ('blog/index.json', 'blog/index.js'):
                path = out / name
                if path.exists() and probe[:80] in re.sub(r'\s+', ' ', searchable.get(path, '')):
                    fail(f'"{label}" is not published until {when} but its text is inside {name}')
                    break



def check_live_urls(out: Path, fail) -> None:
    """Every URL the old site published must still resolve.

    This site replaced a Hugo site that had been live for years. The dangerous
    part of that swap is not the pages you remember, it is the ones you do not:
    a feed URL a reader is still polling, a tag index someone bookmarked, an
    icon path referenced from a cached manifest. Each becomes a 404 the moment
    the new build ships, and nothing in the new build knows they ever existed.

    The list is taken from what the live site actually served, not from the old
    content folder, because that folder also holds drafts that were never
    published and would have produced redirects to nowhere.
    """
    manifest = ROOT / 'live_urls.json'
    if not manifest.exists():
        return
    import json as _json
    paths = _json.loads(manifest.read_text(encoding='utf-8')).get('paths', [])

    for url in paths:
        rel = url.strip('/')
        if not rel:
            target = out / 'index.html'
        elif '.' in Path(rel).name:
            target = out / rel
        else:
            target = out / rel / 'index.html'
        if not target.exists():
            fail(f'{url} was served by the old site and this build has nothing at it. '
                 f'Add a page, or a redirect in redirects.json.')



# Claims on the home page that no longer have a source. If any of these strings
# reappear, something has bypassed the generated statistics and gone back to
# typing numbers into the HTML.
RETIRED_CLAIMS = ('128+', '12K', '40+ ', 'Teams Led')

STATS_MAX_AGE_DAYS = 183

# Kept as a literal rather than imported from build.py so that a typo in the
# builder's own configuration cannot pass its own check.
SITE_URL = 'https://jeffops.com'

# Checked by behaviour rather than by string. A robots.txt rule that a parser
# does not apply is the failure worth catching: the file looks right, the
# policy reads correctly, and the crawler it names is turned away anyway.
# Comments trailing a directive are the usual cause, so the assertion is what a
# real parser concludes, not what the text appears to say.
#
# The policy is open to everything, so the list runs the other way now: nothing
# must be blocked, and a broad sample across search, AI training, AI retrieval
# and aggregation must all get through. A stray Disallow reintroduced by an
# edit fails here rather than quietly removing the site from something.
ROBOTS_MUST_BE_BLOCKED = ()
ROBOTS_MUST_BE_ALLOWED = ('Googlebot', 'bingbot', 'DuckDuckBot', 'Applebot',
                          'GPTBot', 'ClaudeBot', 'anthropic-ai', 'Google-Extended',
                          'Applebot-Extended', 'CCBot', 'FacebookBot', 'Amazonbot',
                          'cohere-ai', 'Bytespider', 'omgili', 'Diffbot', 'img2dataset',
                          'ChatGPT-User', 'OAI-SearchBot', 'Claude-Web',
                          'PerplexityBot', 'YouBot', 'SomeCrawlerNobodyHasNamedYet')


# WCAG AA wants 4.5:1 for body text. These are the backgrounds text actually
# sits on, measured in the browser rather than assumed: the page background, the
# card background, the panel behind a badge, and the cyan wash a tag count sits
# in. A palette change is the one edit that can break contrast everywhere at
# once and look like nothing on screen, so the tokens are checked directly.
CONTRAST_BACKGROUNDS = {
    'the page': (10, 12, 15),
    'a card': (15, 18, 23),
    'a panel': (21, 25, 32),
    'the cyan wash': (9, 33, 39),
}
CONTRAST_MIN = 4.5


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    def channel(value: int) -> float:
        v = value / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    high, low = sorted((_relative_luminance(a), _relative_luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def check_contrast(fail) -> None:
    css = (ROOT / 'css' / 'styles.css').read_text(encoding='utf-8')
    for token in ('--text', '--text-mid', '--text-dim'):
        match = re.search(re.escape(token) + r':\s*#([0-9a-fA-F]{6})', css)
        if not match:
            fail(f'{token} is not defined in styles.css')
            continue
        value = match.group(1)
        rgb = tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))
        for name, background in CONTRAST_BACKGROUNDS.items():
            ratio = contrast_ratio(rgb, background)
            if ratio < CONTRAST_MIN:
                fail(f'{token} (#{value}) is {ratio:.2f}:1 against {name} '
                     f'{background}; WCAG AA wants {CONTRAST_MIN}:1 for body text')


def check_robots(out: Path, fail) -> None:
    from urllib.robotparser import RobotFileParser

    path = out / 'robots.txt'
    if not path.exists():
        fail('robots.txt is missing')
        return

    parser = RobotFileParser()
    parser.parse(path.read_text(encoding='utf-8').splitlines())

    probe = f'{SITE_URL}/posts/'
    for agent in ROBOTS_MUST_BE_BLOCKED:
        if parser.can_fetch(agent, probe):
            fail(f'robots.txt does not actually block {agent}. The rule is either '
                 f'missing or written so a parser ignores it.')
    for agent in ROBOTS_MUST_BE_ALLOWED:
        if not parser.can_fetch(agent, probe):
            fail(f'robots.txt blocks {agent}, which must be allowed to crawl the site')

    # Googlebot is checked against the home page separately from the /posts/
    # probe above. It is the single crawler whose loss costs the most, and a
    # rule that reaches only the root would not show up in the probe.
    if not parser.can_fetch('Googlebot', f'{SITE_URL}/'):
        fail('robots.txt blocks Googlebot from the home page')

    # The policy is that nothing is disallowed, so no Disallow line with a path
    # should exist at all. An empty 'Disallow:' is the RFC 9309 way of spelling
    # "allow everything" and is fine; anything after it is not.
    for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        text = line.split('#', 1)[0].strip()
        if text.lower().startswith('disallow:') and text.split(':', 1)[1].strip():
            fail(f'robots.txt line {number} disallows a path ({text!r}); the site '
                 f'is meant to be open to every crawler')

    sitemaps = parser.site_maps() or []
    if f'{SITE_URL}/sitemap.xml' not in sitemaps:
        fail(f'robots.txt does not declare {SITE_URL}/sitemap.xml as its sitemap')


def check_home_page(out: Path, fail) -> None:
    """The home page must say nothing it cannot support.

    Search metadata and unsupported numbers are checked in the same place
    deliberately: both are things that look fine on screen and are wrong in a
    way only a machine notices. The home page had no description, no canonical
    and no structured data at all, while claiming 128 articles against seven and
    12,000 subscribers against no source.
    """
    home = out / 'index.html'
    if not home.exists():
        return
    markup = home.read_text(encoding='utf-8')

    for tag, what in (('rel="canonical"', 'a canonical link'),
                      ('name="description"', 'a meta description'),
                      ('application/ld+json', 'structured data')):  # noqa: E501
        if tag not in markup:
            fail(f'the home page is missing {what}, on the one URL most likely to '
                 f'rank for the author\'s own name')

    # The "As seen at" strip is the most quotable claim on the site and the
    # easiest for a reader in the same community to check. It listed seven
    # conferences Jeff had never spoken at. Every name must now come from
    # events.json, so an addition is a deliberate edit to a sourced file rather
    # than a line of markup nobody reviews.
    events_file = ROOT / 'events.json'
    strip = re.search(r'<div class="logos-track">(.*?)\n?\s*</div>', markup, re.DOTALL)
    if events_file.exists():
        import json as _json
        declared = set(_json.loads(events_file.read_text(encoding='utf-8')).get('events', []))
        if not strip:
            fail('the "As seen at" strip is missing from the home page')
        else:
            shown = [re.sub(r'<[^>]+>', '', item).strip()
                     for item in re.findall(r'<span class="logo-item">(.*?)</span>\s*(?=<span class="logo-item"|$)',
                                            strip.group(1), re.DOTALL)]
            shown = [x for x in (re.sub(r'\s+', ' ', s2).strip() for s2 in shown) if x]
            if not shown:
                fail('the "As seen at" strip rendered no events')
            for name in shown:
                if name not in declared:
                    fail(f'the "As seen at" strip shows "{name}", which is not in '
                         f'events.json. Every event named there must be one Jeff '
                         f'actually spoke at.')

    for src in set(re.findall(r'<img[^>]+src="([^"]+)"', markup)) | set(
            re.findall(r'data-portraits="([^"]*)"', markup)):
        for candidate in re.split(r'[,]', src):
            name = candidate.split('|')[0].strip()
            if not name or name.startswith(('http', 'data:', '/')):
                continue
            if not (out / name).exists():
                fail(f'the home page references the image "{name}" and the build did '
                     f'not produce it, so it renders broken')

    leftover = re.search(r'\{(posts|talks|editions|description)\}', markup)
    if leftover:
        fail(f'the home page still contains the placeholder {leftover.group(0)}, '
             f'so a count was never substituted')

    # One description, in three places. They are filled from a single source, so
    # any disagreement means an injection missed one and a link preview is
    # quoting something nobody has read in a year. That is exactly how the home
    # page came to advertise itself to LinkedIn with a line left over from the
    # previous site.
    descriptions = {
        'meta description': re.search(r'<meta name="description" content="([^"]*)"', markup),
        'og:description': re.search(r'<meta property="og:description" content="([^"]*)"', markup),
        'twitter:description': re.search(r'<meta name="twitter:description" content="([^"]*)"', markup),
    }
    found = {}
    for label, match in descriptions.items():
        if not match:
            fail(f'the home page has no {label}')
        elif not match.group(1).strip():
            fail(f'the home page {label} is empty')
        else:
            found[label] = match.group(1)
    if len(set(found.values())) > 1:
        for label, value in found.items():
            fail(f'home page descriptions disagree: {label} = "{value[:70]}..."')

    stats = re.search(r'<div class="stats-bar">(.*?)\n?\s*</div>(?!\s*<div class="stat-cell")',
                      markup, re.DOTALL)
    if not stats:
        fail('the home page statistics block is missing')
    else:
        block = stats.group(1)
        # Counted separately from the retired-claim scan below: the first version
        # of this check used a non-greedy match that stopped at the first
        # </div>, so it inspected one cell out of four and three hand-written
        # figures sailed past it.
        rendered = block.count('class="stat-cell"')
        generated = len(re.findall(r'class="stat-val">[^<]*</span>', block))
        if rendered != generated:
            fail(f'the statistics block has {rendered} cell(s) but {generated} value(s); '
                 f'the injection did not replace the whole block')
        if not block.strip():
            fail('the home page statistics block is empty')
        for claim in RETIRED_CLAIMS:
            if claim in block:
                fail(f'the home page statistics contain "{claim}", which is a '
                     f'hand-written number with no source. Every figure there must '
                     f'be counted at build time or declared in stats.json.')

    # Declared image dimensions are a promise about a file. If they drift, the
    # crawler lays out a space of one size and drops an image of another into
    # it, and the only place that shows up is somebody else's timeline.
    card = out / 'og-card.png'
    declared_w = re.search(r'<meta property="og:image:width" content="(\d+)"', markup)
    declared_h = re.search(r'<meta property="og:image:height" content="(\d+)"', markup)
    if not (declared_w and declared_h):
        fail('the home page does not declare og:image:width and og:image:height, '
             'so a crawler must fetch the card before it can size the preview')
    elif not card.exists():
        fail('og-card.png is missing from the build, but the page advertises it')
    else:
        try:
            from PIL import Image
            with Image.open(card) as im:
                real = im.size
            if real != (int(declared_w.group(1)), int(declared_h.group(1))):
                fail(f'og:image is declared {declared_w.group(1)}x{declared_h.group(1)} '
                     f'but og-card.png is actually {real[0]}x{real[1]}')
        except ImportError:
            pass

    # A figure in stats.json is a promise that somebody checked it on a date.
    path = ROOT / 'stats.json'
    if path.exists():
        import json as _json
        today = datetime.now(timezone.utc).date()
        for key, meta in _json.loads(path.read_text(encoding='utf-8')).get('stats', {}).items():
            if meta.get('value') in (None, ''):
                continue
            checked = meta.get('verified')
            if not checked:
                fail(f'stats.json: "{key}" has a value but no verified date')
                continue
            try:
                age = (today - datetime.fromisoformat(str(checked)).date()).days
            except ValueError:
                fail(f'stats.json: "{key}" has an unparseable verified date {checked!r}')
                continue
            if age > STATS_MAX_AGE_DAYS:
                fail(f'stats.json: "{key}" was last verified {age} days ago. '
                     f'Re-check the number or clear the value.')


def check_speaking(out: Path, fail) -> None:
    """No talk may advertise itself as upcoming after it has happened.

    Two sat on the live site marked Upcoming for conferences 502 and 557 days
    past. Status is now derived from the date at build time, so this asserts the
    derivation rather than the data, and it is the daily build that flips a talk
    from upcoming to past on the right morning.
    """
    path = out / 'speaking_talks.json'
    if not path.exists():
        return
    import json as _json
    today = datetime.now(timezone.utc).date()
    for talk in _json.loads(path.read_text(encoding='utf-8')):
        try:
            when = datetime.fromisoformat(str(talk.get('date'))).date()
        except (TypeError, ValueError):
            fail(f'speaking_talks.json: {talk.get("event", "?")!r} has an unusable date '
                 f'{talk.get("date")!r}')
            continue
        expected = 'Upcoming' if when >= today else 'Past'
        if talk.get('status') != expected:
            fail(f'{talk.get("event", "?")} on {when} is marked '
                 f'{talk.get("status")!r} but should be {expected!r}')

    page = out / 'speaking' / 'index.html'
    if page.exists() and 'class="talk-item"' not in page.read_text(encoding='utf-8'):
        fail('/speaking/ renders no talks without JavaScript, so a crawler sees an '
             'empty page')


def check_picture_sources(out: "Path", fail) -> None:
    """Every <picture> source in the WHOLE build resolves to a file.

    This rule already existed, but only inside the post loop — so it saw posts and newsletter
    editions and never the pages build_promoted_pages() lifts out of index.html. /about/ shipped
    <source srcset="JeffOps_Finger.webp"> for months, resolving to /about/JeffOps_Finger.webp,
    a 404, while the file sat at the build root. A browser that has matched a <source> does not
    fall back to the <img> when its resource fails: it paints nothing. So the avatar was blank for
    every WebP-capable visitor, and CI called it green on every single run.

    Checking every *.html rather than a curated list is the point. The bug was not that the rule
    was wrong, it was that the rule was applied to a subset nobody re-examined when a new page
    type appeared.
    """
    for page in sorted(out.rglob('*.html')):
        label = page.relative_to(out).as_posix()
        source = page.read_text(encoding='utf-8', errors='replace')
        for block in re.findall(r'<picture>.*?</picture>', source, re.S):
            for attr, value in re.findall(r'\b(srcset|src)="([^"]+)"', block):
                for candidate in (value.split(',') if attr == 'srcset' else [value]):
                    url = candidate.strip().split()[0] if candidate.strip() else ''
                    if not url or url.startswith(('http', 'data:', '//')):
                        continue
                    target = (out / url.lstrip('/')) if url.startswith('/') \
                        else (page.parent / url)
                    if not target.exists():
                        fail(f'{label} — <picture> {attr} candidate "{url}" does not resolve')


def check_highlighter_is_earned(out: "Path", fail) -> None:
    """Code blocks arrive highlighted, and no static page pays for a runtime highlighter.

    Highlighting moved to build time on 2026-08-31. Before that this checked whether a page loaded
    highlight.min.js, in both directions, and both directions had already caught a real bug — a page
    pulling in 121 KB to highlight nothing, and later every page on the site silently losing
    highlighting when the markup changed shape. The premise is what changed, not the need.

    What it asserts now:
      a page with a tagged code block carries Pygments markup, so highlighting actually ran;
      a page with any code block links the stylesheet, or those spans are colourless;
      no static page loads highlight.min.js at all, which is the whole saving.

    The single-page app is exempt and deliberately so: it parses markdown in the browser, so
    post-enhance.js fetches the runtime highlighter on demand. That reference lives in a .js file,
    not in any page's markup, so it does not trip the last rule.
    """
    for page in sorted(out.rglob('*.html')):
        source = page.read_text(encoding='utf-8', errors='replace')
        label = page.relative_to(out).as_posix()
        if 'data-preview-build' in source:
            continue

        has_block = re.search(r'<pre[^>]*><code', source) is not None
        # A block that named its language is one Pygments should have been able to colour. An
        # untagged block has no lexer to pick and is left as plain text on purpose.
        tagged = re.findall(r'<pre[^>]*><code class="language-([\w+-]+)">(.*?)</code></pre>',
                            source, re.S)
        highlightable = [(lang, body) for lang, body in tagged if lang.lower() != 'mermaid']

        if 'highlight.min.js' in source:
            fail(f'{label} — loads the runtime syntax highlighter; highlighting is done at build '
                 f'time and this is 121 KB for nothing')

        for lang, body in highlightable:
            if '<span class=' not in body:
                fail(f'{label} — the {lang} block shipped unhighlighted; either Pygments has no '
                     f'lexer for it or highlight_code_blocks did not run')

        if has_block and '/css/code.css' not in source:
            fail(f'{label} — has a code block but does not link the highlighting stylesheet, so '
                 f'its spans have no colours')


def check_feed_images_absolute(out: "Path", fail) -> None:
    """No relative image src survives into a feed body.

    There is no xml:base in the feed, so a reader resolves a relative src against the feed
    document itself — https://jeffops.com/rss.xml — and asks for https://jeffops.com/<filename>,
    which 404s. All 17 images in <content:encoded> were doing this: the MTA-STS post is a
    13-screenshot walkthrough that is unfollowable without them, and a full-text feed body cannot
    be recalled once a subscriber has pulled it.
    """
    for name in ('rss.xml', 'index.xml'):
        feed = out / name
        if not feed.is_file():
            continue
        text = feed.read_text(encoding='utf-8', errors='replace')
        for block in re.findall(r'<content:encoded>.*?</content:encoded>', text, re.S):
            for src in re.findall(r'<img\b[^>]*?\bsrc="([^"]+)"', block):
                if not src.startswith(('http://', 'https://', 'data:')):
                    fail(f'{name} — feed body image "{src}" is relative and will 404 for '
                         f'subscribers; it must be absolute')


def check_accessible_controls(out: "Path", fail) -> None:
    """Form controls are labelled, and anything that acts like a link is one.

    Both halves of this shipped green for the life of the site. Twelve labels carried the visible
    text and no `for`, so a screen reader announced "edit, blank", clicking a label focused nothing
    and voice control could not say "click Email" — on the forms that compose the only mailto: into
    the inbox. And the hero's eight navigation nodes were <div data-page="..."> wired from a
    delegated click listener: the visually dominant navigation on the landing page, announced as
    plain text and unreachable without a mouse.

    Neither is the kind of thing a human notices by looking, which is why both need a check rather
    than a resolution to be careful.
    """
    for page in sorted(out.rglob('*.html')):
        label = page.relative_to(out).as_posix()
        source = page.read_text(encoding='utf-8', errors='replace')

        labelled = set(re.findall(r'<label[^>]*\bfor="([^"]+)"', source))
        for match in re.finditer(r'<(input|select|textarea)\b([^>]*)>', source):
            attrs = match.group(2)
            if 'type="hidden"' in attrs:
                continue
            control_id = re.search(r'id="([^"]+)"', attrs)
            if control_id and control_id.group(1) in labelled:
                continue
            if 'aria-label' in attrs or 'aria-labelledby' in attrs:
                continue
            named = control_id.group(1) if control_id else attrs.strip()[:40]
            fail(f'{label} — <{match.group(1)}> "{named}" has no label, aria-label or '
                 f'aria-labelledby')

        # data-page is what the delegated router listens for. On a div it is a mouse-only control.
        for match in re.finditer(r'<(\w+)([^>]*\bdata-page="[^"]*"[^>]*)>', source):
            tag, attrs = match.group(1), match.group(2)
            if tag in ('a', 'button'):
                continue
            if 'tabindex=' in attrs and 'role=' in attrs:
                continue
            page_name = re.search(r'data-page="([^"]*)"', attrs)
            fail(f'{label} — <{tag} data-page="{page_name.group(1) if page_name else "?"}"> is '
                 f'click-only; it needs to be an <a href> or carry role and tabindex')


def check_pages_are_linked(out: "Path", fail) -> None:
    """Every page the build promotes is reachable from somewhere other than itself.

    /consulting/, /training/, /speaking/ and /about/ each had ZERO inbound internal links while the
    home page had 417, because the nav pointed at fragments — and the home page carries a near
    verbatim copy of each of those pages' text. Both copies were indexable and each canonicalised
    to itself, so nothing told a search engine which was the real one; it picked the one with the
    links. A page titled "JeffOps - Training" existed and was the one least likely to be shown.

    A page with no inbound link is not necessarily wrong, but for these four it meant the
    commercial pages were invisible as themselves. Checking the link graph is the only way to
    notice: nothing about the page itself looks broken.
    """
    counts: dict[str, int] = {}
    for page in sorted(out.rglob('*.html')):
        rel = page.relative_to(out).as_posix()
        own = '/' + (rel.rsplit('/', 1)[0] + '/' if '/' in rel else '')
        source = page.read_text(encoding='utf-8', errors='replace')
        if 'noindex' in source:
            continue          # a redirect stub's links are not endorsements
        for href in re.findall(r'href="([^"]+)"', source):
            if href.startswith(('http', 'mailto:', '//')):
                continue
            target = href.split('#')[0] or '/'
            if target.startswith('/') and target != own:
                counts[target] = counts.get(target, 0) + 1

    for section in ('consulting', 'training', 'speaking', 'about'):
        url = f'/{section}/'
        if not (out / section / 'index.html').is_file():
            continue
        if not counts.get(url):
            fail(f'{url} is built but nothing links to it — it competes with the copy of the same '
                 f'text on the home page and loses')


def withheld_editions() -> list[dict]:
    """Newsletter editions the build must not publish: drafts, and anything dated ahead.

    Read from the source tree rather than asked of build.py, for the same reason check_schedule
    searches the output instead of trusting the render: a verifier that shares the build's idea of
    what is published cannot catch the build being wrong about it.
    """
    out = []
    folder_root = ROOT / 'newsletter'
    if not folder_root.is_dir():
        return out
    today = datetime.now(timezone.utc).date().isoformat()
    for folder in sorted(p for p in folder_root.iterdir() if p.is_dir()):
        if folder.name.startswith('_'):
            continue
        sources = [f for f in sorted(folder.iterdir())
                   if f.is_file() and f.suffix.lower() in ('.md', '.markdown')]
        if not sources:
            continue
        text = sources[0].read_text(encoding='utf-8', errors='replace')
        front = {}
        m = re.match(r'^---\s*\n(.*?)\n---\s*\n', text, re.S)
        if m:
            for line in m.group(1).splitlines():
                if ':' in line:
                    k, v = line.split(':', 1)
                    front[k.strip().lower()] = v.strip().strip('"\'')
        draft = front.get('draft', '').strip().lower() in ('1', 'true', 'yes', 'on')
        date = front.get('date', '')[:10]
        if draft or (date and date > today):
            out.append({'folder': folder.name,
                        'slug': front.get('slug', '') or folder.name,
                        'title': front.get('title', folder.name),
                        'why': 'draft' if draft else f'dated {date}'})
    return out


def check_newsletter_schedule(out: "Path", fail) -> None:
    """A withheld edition appears nowhere in the output.

    load_editions() hardcoded 'is_published': True, so `draft: true` on an edition did nothing and a
    future date published immediately - into the page, both feeds, the sitemap and the home-page
    archive. check_schedule's docstring says "Nothing unpublished may appear anywhere in the
    output", and it meant it, but it globs posts/ and blog/ and has never looked at newsletter/.

    The feed carries the full body, so a subscriber pull cannot be recalled. That is why this checks
    the built bytes rather than the build's intent.
    """
    pending = withheld_editions()
    if not pending:
        return

    searchable = {}
    for path in out.rglob('*'):
        if path.is_file() and path.suffix in ('.html', '.xml', '.json', '.js', '.txt', '.md'):
            searchable[path] = path.read_text(encoding='utf-8', errors='ignore')

    for edition in pending:
        needles = {edition['slug'], edition['folder']}
        needles = {n for n in needles if len(n) > 3}
        for path, text in searchable.items():
            for needle in needles:
                if needle in text:
                    fail(f'withheld newsletter edition ({edition["why"]}) "{edition["title"][:40]}" '
                         f'leaks into {path.relative_to(out).as_posix()} via "{needle}"')
                    break


# What the policy has to say, not merely which directives it mentions. An empty set means the
# directive must be present and its value is not asserted here.
# Scripts that write to the DOM, and therefore need the Trusted Types policy installed ahead of
# them. app.js, post-enhance.js, highlight.min.js and marked.min.js each genuinely use a sink.
# post-page.js is listed conservatively: it has none today, but it ships only alongside the ones
# that do, so requiring the policy with it costs nothing and errs in the safe direction.
#
# forms.js is deliberately absent, and that is the whole point of this list. It touches .value,
# .textContent, .style.display and location.href — no innerHTML, no insertAdjacentHTML, no
# document.write, no new Function. The five promoted pages load it and nothing else.
SINK_SCRIPTS = ('app.js', 'post-enhance.js', 'post-page.js', 'highlight.min.js', 'marked.min.js')


REQUIRED_CSP = {
    'default-src': {"'none'"},
    'script-src': {"'self'"},
    'base-uri': {"'none'"},
    'object-src': {"'none'"},
    'require-trusted-types-for': {"'script'"},
}


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else '_site')
    if not out.is_absolute():
        out = (ROOT / out).resolve()

    failures: list[str] = []
    checked = 0

    def fail(message: str) -> None:
        failures.append(message)
        print(f'  FAIL  {message}')

    if not out.exists():
        print(f'No build directory at {out}')
        return 1

    print(f'Verifying {out}\n')

    posts = collect_posts()
    if not posts:
        fail('no posts were collected — the blog directory looks empty')

    for post in posts:
        page = out / post['url'].strip('/') / 'index.html'
        label = post['url']
        if not page.exists():
            fail(f'{label} — page was not generated')
            continue

        source = page.read_text(encoding='utf-8')
        text = visible_text(source)
        checked += 1

        # 1. The article body must be in the HTML, not only in the JSON index.
        probes_found = probes(post["body_markdown"])[:5]
        if not probes_found:
            fail(f'{label} — no prose long enough to verify; post may be empty')
        else:
            missing = [p for p in probes_found if p not in text]
            if missing:
                fail(f'{label} — article text missing from the rendered HTML '
                     f'({len(missing)}/{len(probes_found)} passages absent, '
                     f'first: {missing[0][:60]!r})')

        # 2. Metadata that determines how the page is indexed and previewed.
        canonical = re.search(r'<link rel="canonical" href="([^"]+)"', source)
        if not canonical:
            fail(f'{label} — no canonical link')
        elif not canonical.group(1).startswith('http'):
            fail(f'{label} — canonical is not absolute: {canonical.group(1)}')

        description = re.search(r'<meta name="description" content="([^"]*)"', source)
        if not description or len(description.group(1).strip()) < 20:
            fail(f'{label} — missing or too-short meta description')

        if '<title>' not in source or '<title></title>' in source:
            fail(f'{label} — missing title')

        if 'application/ld+json' not in source:
            fail(f'{label} — no JSON-LD structured data')

        # 3. An unreplaced placeholder means a template field was never filled.
        leftover = re.search(r'\{(lang|title|content|canonical|nav|footer|toc)\}', source)
        if leftover:
            fail(f'{label} — unreplaced template placeholder {leftover.group(0)}')

        # 4. An author TODO must never reach production. These mark passages
        # that need a real detail from Jeff rather than an invented one, and a
        # plausible-sounding placeholder is exactly the kind of thing that
        # survives a proofread. Markdown passes HTML comments straight through,
        # so the marker is invisible on the page and would otherwise ship
        # silently.
        todo = re.search(r'TODO\(jeff\):?\s*(.{0,80})', source, re.I | re.S)
        if todo:
            note = re.sub(r'\s+', ' ', todo.group(1)).strip()
            fail(f'{label} — unresolved author TODO: "{note}…"')

        # 5. A callout marker still visible in the prose means the blockquote it
        # opened was never converted — either the type is misspelt, or two
        # callouts were written back to back, which the markdown parser merges
        # into one blockquote so only the first marker sits at the start. Either
        # way the reader sees a literal "[!WARNING]", so it fails the build
        # rather than shipping.
        marker = re.search(r'\[!([A-Za-z]+)\]', text)
        if marker:
            fail(f'{label} — unrendered callout marker "[!{marker.group(1)}]" in the '
                 f'body. Check the spelling, and leave a blank line and some prose '
                 f'between consecutive callouts.')

        # 6. A <source> in a <picture> has no fallback of its own: if the file
        # it names is missing, the browser does not quietly use the <img>, it
        # paints nothing. So every srcset and every src inside a picture has to
        # resolve to a file that was actually written.
        for block in re.findall(r'<picture>.*?</picture>', source, re.S):
            for attr, value in re.findall(r'\b(srcset|src)="([^"]+)"', block):
                # A srcset is a comma-separated list of candidates, each a URL
                # and an optional descriptor. Checking the whole string as one
                # path passes nothing and fails everything.
                for candidate in (value.split(',') if attr == 'srcset' else [value]):
                    url = candidate.strip().split()[0] if candidate.strip() else ''
                    if not url or url.startswith(('http', 'data:', '//')):
                        continue
                    target = (out / url.lstrip('/')) if url.startswith('/') \
                        else (page.parent / url)
                    if not target.exists():
                        fail(f'{label} — <picture> {attr} candidate "{url}" '
                             f'does not resolve to a file')

        # 7. Heading ids are the contract behind every deep link and every
        # anchor. A heading without one silently drops out of the table of
        # contents and cannot be linked to.
        body = re.search(r'<div class="post-content" id="post-content">(.*?)\n\s*</div>',
                         source, re.S)
        if body:
            headless = [h for h in re.findall(r'<(h2|h3)(\s[^>]*)?>', body.group(1))
                        if 'id=' not in (h[1] or '')]
            if headless:
                fail(f'{label} — {len(headless)} heading(s) rendered without an id')

    # 4. Feeds and crawler files must exist and parse.
    for name in ('sitemap.xml', 'rss.xml'):
        path = out / name
        if not path.exists():
            fail(f'{name} was not generated')
            continue
        try:
            ET.parse(path)
        except ET.ParseError as exc:
            fail(f'{name} is not valid XML: {exc}')

    for name in ('robots.txt', 'index.html', 'posts/index.html', 'CNAME', '.nojekyll'):
        if not (out / name).exists():
            fail(f'{name} is missing')

    # Every asset is served from this origin. A third-party script or font
    # reintroduced by hand costs two DNS lookups and two TLS handshakes before
    # the page can paint, buys no shared cache (browsers partitioned that by
    # site in 2020), and in the case of Google Fonts hands every visitor's IP
    # address to a third party. Mermaid is the one deliberate exception: it is
    # 875KB gzipped and fetched by post-enhance.js only if a diagram exists, so
    # it is allowed in a script body but not in a tag the page loads eagerly.
    for page in sorted(out.rglob('*.html')):
        markup = page.read_text(encoding='utf-8', errors='ignore')
        for tag in re.findall(r'<(?:script|link)\b[^>]*>', markup):
            url = re.search(r'(?:src|href)="(https?://[^"]+)"', tag)
            if url and 'jeffops.com' not in url.group(1):
                fail(f'/{page.relative_to(out).as_posix()} loads {url.group(1)} '
                     f'from another origin')

    # The Content Security Policy has to be on every page, and it has to still
    # be worth having. An inline event handler anywhere would force
    # 'unsafe-inline' back into script-src, at which point the policy stops
    # defending against the thing it exists for — so both are checked, and the
    # handler check is the one that will actually catch a regression, because
    # writing onclick="" is the natural thing to reach for.
    policies_seen: dict[str, list[str]] = {}
    for page in sorted(out.rglob('*.html')):
        label = '/' + page.relative_to(out).as_posix()
        markup = page.read_text(encoding='utf-8', errors='ignore')

        csp = re.search(r'<meta http-equiv="Content-Security-Policy" content="([^"]+)"', markup)
        if not csp:
            fail(f'{label} has no Content Security Policy')
            continue
        policy = csp.group(1)
        policies_seen.setdefault(policy, []).append(label)

        # Parsed into directive -> tokens, rather than asking whether a directive NAME appears
        # anywhere in the string. The old form spelled out the values it wanted and then threw every
        # one of them away with .split()[0], so a policy reading
        #     default-src *; base-uri https://attacker.example; object-src *; script-src https://…
        # satisfied every check. The 'unsafe-inline' test had the same shape: it searched the text
        # before the first occurrence of 'style-src', so the same token written after style-src was
        # invisible. Both were order-dependent string matching standing in for the one control this
        # site's whole no-inline-script design rests on.
        parsed = {}
        for chunk in policy.split(';'):
            parts = chunk.split()
            if parts:
                parsed[parts[0]] = set(parts[1:])

        for name, required in REQUIRED_CSP.items():
            if name not in parsed:
                fail(f'{label} — CSP is missing {name}')
            elif required and not required.issubset(parsed[name]):
                missing = ', '.join(sorted(required - parsed[name]))
                fail(f'{label} — CSP {name} is missing {missing} (has: '
                     f'{" ".join(sorted(parsed[name])) or "nothing"})')

        for name in ('script-src', 'default-src'):
            tokens = parsed.get(name, set())
            if "'unsafe-inline'" in tokens:
                fail(f'{label} — CSP {name} allows inline script, which defeats it')
            if "'unsafe-eval'" in tokens:
                fail(f'{label} — CSP {name} allows eval')
            if '*' in tokens:
                fail(f'{label} — CSP {name} allows any origin')

        # The policy is four verbatim copies in build.py, with nothing asserting they agree. All
        # pages carrying one identical policy today is luck, not a check.
        handlers = re.findall(r'\son[a-z]+\s*=\s*["\']?[^>\s]', markup)
        if handlers:
            fail(f'{label} carries {len(handlers)} inline event handler(s); '
                 f'they cannot run under this CSP and would need unsafe-inline')

        # An inline <script> is blocked outright and fails silently — the page
        # renders, nothing throws, and the script simply never runs. That is
        # exactly how the redirect stubs kept working off their meta refresh
        # while their inline location.replace had been dead since the policy
        # shipped. JSON-LD is exempt: it is data, and browsers do not execute it.
        for attrs, body in re.findall(r'<script([^>]*)>(.*?)</script>', markup, re.S):
            if 'src=' in attrs or 'application/ld+json' in attrs:
                continue
            if body.strip():
                fail(f'{label} has an inline <script>, which this CSP blocks; '
                     f'it would never run')

        # Exactly one main landmark. None means a screen reader has no way past
        # the navigation but to tab through it; more than one means there is no
        # unambiguous target, which is the same problem wearing a rosette.
        mains = len(re.findall(r'<main[\s>]', markup))
        if mains != 1:
            fail(f'{label} has {mains} <main> landmark(s); it needs exactly one')

        # Only pages that run a script which WRITES TO THE DOM need the policy installed. The
        # comment here used to say "adding a sanitiser to a page with nothing to sanitise is bytes
        # for the sake of a green tick" and then required it on any page running any script at all —
        # which is how /about, /consulting, /training, /speaking and /security-policy came to ship
        # purify plus the policy, 10.7 KB gzipped, for forms.js, which has no sink in it.
        #
        # Keyed on the script rather than on "has any script", so the requirement follows the thing
        # that creates the risk. A page with only forms.js still sends
        # require-trusted-types-for 'script', so if a sink ever appears there it throws rather than
        # running unsanitised — the sanitiser has to come back with the sink, not before it.
        scripts = re.findall(r'<script[^>]*\bsrc=["\']?([^"\'\s>]+)', markup)
        if any(any(sink in s for sink in SINK_SCRIPTS) for s in scripts):
            if not any('trusted-types.js' in s for s in scripts):
                fail(f'{label} runs a script that writes to the DOM but does not install the '
                     f'Trusted Types policy')
            elif not any('purify' in s for s in scripts):
                fail(f'{label} installs the policy without the sanitiser it depends on')
            else:
                order = [i for i, s in enumerate(scripts)
                         if 'purify' in s or 'trusted-types.js' in s]
                first_other = next((i for i, s in enumerate(scripts)
                                    if 'purify' not in s and 'trusted-types.js' not in s), None)
                if first_other is not None and first_other < max(order):
                    fail(f'{label} loads {scripts[first_other]} before the Trusted '
                         f'Types policy is installed')

    check_contrast(fail)
    check_robots(out, fail)
    check_security_txt(out, fail)
    check_schedule(out, fail)
    check_live_urls(out, fail)
    check_home_page(out, fail)
    check_speaking(out, fail)
    check_picture_sources(out, fail)
    check_highlighter_is_earned(out, fail)
    check_feed_images_absolute(out, fail)
    check_accessible_controls(out, fail)
    check_pages_are_linked(out, fail)
    check_newsletter_schedule(out, fail)

    # One policy, everywhere. It is written out four times in build.py and nothing has ever asserted
    # the four agree; every page carrying the same one today is luck.
    if len(policies_seen) > 1:
        for policy, pages in sorted(policies_seen.items(), key=lambda kv: -len(kv[1])):
            fail(f'{len(pages)} page(s) carry a distinct CSP, e.g. {pages[0]}: {policy[:90]}...')

    # 5. The subscribe path must not lie.
    #
    # The original form cleared its input and displayed "✓ You're subscribed!"
    # while storing and sending nothing — every address entered was discarded
    # after telling the visitor it had worked. That is the one bug on this site
    # that costs something irreplaceable, so it gets a permanent guard rather
    # than a fix and a hope.
    home = out / 'index.html'
    if home.exists():
        markup = home.read_text(encoding='utf-8')

        if re.search(r"you'?re subscribed|thanks for subscribing|✓ subscribed", markup, re.I):
            fail('index.html shows a subscription confirmation — only a backend '
                 'that has actually received the address may confirm one')

        if 'PASTE-YOUR-NEWSLETTER-URL' in markup:
            fail('the newsletter link is still a placeholder')

        link = re.search(r'id="nl-subscribe"[^>]*href="([^"]+)"', markup)
        if not link:
            fail('index.html has no subscribe link (expected id="nl-subscribe")')
        elif not re.match(r'https://www\.linkedin\.com/newsletters/[\w-]+/?$', link.group(1)):
            fail(f'subscribe link does not point at a LinkedIn newsletter: {link.group(1)}')

        # 6. The newsletter archive must be rendered, and must point at real
        # editions. An empty or unreplaced list means the injection silently
        # failed and the page ships with no archive at all.
        archive = re.search(r'<div class="issue-list" id="issue-list">(.*?)</div>\s*\n\s*</div>',
                            markup, re.DOTALL)
        if not archive:
            fail('index.html has no newsletter archive container')
        else:
            hrefs = re.findall(r'<a class="issue-item"[^>]*href="([^"]+)"', archive.group(1))
            if not hrefs:
                fail('the newsletter archive rendered no editions')
            # Two destinations are legitimate now that editions are republished
            # here: an on-site copy, or the LinkedIn original for an edition not
            # carried across yet. Anything else is a broken row.
            for href in hrefs:
                if href.startswith('https://www.linkedin.com/pulse/'):
                    continue
                if href.startswith('/newsletter/') and href.endswith('/'):
                    if not (out / href.strip('/') / 'index.html').exists():
                        fail(f'archive links to {href}, which was never rendered')
                    continue
                fail(f'archive entry points somewhere unexpected: {href}')

            if 'Generated at build time' in archive.group(1):
                fail('the newsletter archive still contains its build-time placeholder')

    # 6b. Every republished edition must credit the original. Copying Jeff's own
    # writing onto his own site is fine; publishing it with no statement of where
    # it first appeared, and no way to reach it, is not. That is exactly the
    # detail that goes missing when a page is generated rather than written, so
    # it is checked rather than trusted.
    #
    # newsletter_editions.json used to be cross-checked here against the rendered
    # row count. The file is gone: editions are markdown files now, and a count of
    # a second list could only ever disagree with the first.
    edition_dir = out / 'newsletter'
    if edition_dir.is_dir():
        for page in sorted(edition_dir.glob('*/index.html')):
            url = f'/newsletter/{page.parent.name}/'
            text = page.read_text(encoding='utf-8')
            if 'edition-origin' not in text:
                fail(f'{url} does not say where the edition was first published')
            origin = re.search(r'class="edition-origin-link" href="([^"]+)"', text)
            if not origin:
                fail(f'{url} has no link to the original on LinkedIn')
            elif not origin.group(1).startswith('https://www.linkedin.com/pulse/'):
                fail(f'{url} credits a non-LinkedIn original: {origin.group(1)}')
            canonical = re.search(r'<link rel="canonical" href="([^"]+)"', text)
            if not canonical:
                fail(f'{url} has no canonical URL')
            elif canonical.group(1) != SITE_URL + url:
                fail(f'{url} is canonical to {canonical.group(1)}, not to itself')
            if re.search(r'TODO\(jeff\)', text):
                fail(f'{url} still carries the edition placeholder, so it was '
                     f'rendered from a stub rather than from the real text')
            body = re.search(r'<div class="post-content" id="post-content">(.*?)</div>\s*<div id="related-section"',
                             text, re.DOTALL)
            if body and len(re.sub(r'<[^>]+>', '', body.group(1)).split()) < 150:
                fail(f'{url} has fewer than 150 words of body text, which is not '
                     f'a newsletter edition')

            # A cover that does not resolve fails in two places at once: a
            # broken image on the page, and a dead og:image in every share
            # card. The second is the one nobody sees, because it only shows
            # up in someone else's timeline.
            # The <picture> wrapper is optional here on purpose: a cover only
            # gains one when the build wrote it a WebP. Matching the <img>
            # wherever it sits inside the figure means adding or removing that
            # wrapper cannot quietly switch this check off, which is what
            # happened the first time — the old pattern required the img to
            # follow the figure tag directly, and stopped matching anything the
            # day a <picture> appeared between them.
            cover = re.search(r'<figure class="post-cover">.*?<img src="([^"]+)"([^>]*)>',
                              text, re.DOTALL)
            if cover:
                if not (out / cover.group(1).lstrip('/')).is_file():
                    fail(f'{url} shows a cover image at {cover.group(1)}, '
                         f'which was never written to the build')
                if 'alt=' not in cover.group(2):
                    fail(f'{url} has a cover image with no alt attribute')
            elif 'post-cover' in text:
                fail(f'{url} has a cover figure with no <img> inside it')

            # Same rule as on the post pages: a <source> that names a missing
            # file paints nothing, it does not fall back to the <img>.
            for block in re.findall(r'<picture>.*?</picture>', text, re.S):
                for attr, value in re.findall(r'\b(srcset|src)="([^"]+)"', block):
                    for candidate in (value.split(',') if attr == 'srcset' else [value]):
                        target_url = candidate.strip().split()[0] if candidate.strip() else ''
                        if not target_url or target_url.startswith(('http', 'data:', '//')):
                            continue
                        target = (out / target_url.lstrip('/')) if target_url.startswith('/') \
                            else (page.parent / target_url)
                        if not target.exists():
                            fail(f'{url} — <picture> {attr} candidate '
                                 f'"{target_url}" does not resolve')
            og = re.search(r'<meta property="og:image" content="([^"]+)"', text)
            if og:
                local = og.group(1).replace(SITE_URL, '', 1).lstrip('/')
                if not (out / local).is_file():
                    fail(f'{url} advertises og:image {og.group(1)}, which does not '
                         f'exist in the build, so every share card would be blank')

    if (out / 'sitemap.xml').exists():
        sitemap = (out / 'sitemap.xml').read_text(encoding='utf-8')
        for post in posts:
            if post['url'] not in sitemap:
                fail(f'{post["url"]} is missing from sitemap.xml')

    print(f'\nChecked {checked} post page(s).')
    if failures:
        print(f'{len(failures)} problem(s) found — not safe to deploy.')
        return 1
    print('All checks passed.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
