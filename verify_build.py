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
# policy reads correctly, and the crawler it names walks straight in. Comments
# trailing a directive are the usual cause, so the assertion is what a real
# parser concludes, not what the text appears to say.
ROBOTS_MUST_BE_BLOCKED = ('GPTBot', 'ClaudeBot', 'anthropic-ai', 'Google-Extended',
                          'Applebot-Extended', 'CCBot', 'FacebookBot', 'Amazonbot',
                          'cohere-ai', 'Bytespider', 'omgili', 'Diffbot', 'img2dataset')
ROBOTS_MUST_BE_ALLOWED = ('Googlebot', 'bingbot', 'ChatGPT-User', 'OAI-SearchBot',
                          'Claude-Web', 'PerplexityBot', 'YouBot')


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

    # Googlebot is the one that must never be caught by a broad rule aimed at
    # Google-Extended. They are separate tokens and blocking the wrong one
    # removes the site from Google Search altogether.
    if not parser.can_fetch('Googlebot', f'{SITE_URL}/'):
        fail('robots.txt blocks Googlebot from the home page')

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
    for page in sorted(out.rglob('*.html')):
        label = '/' + page.relative_to(out).as_posix()
        markup = page.read_text(encoding='utf-8', errors='ignore')

        csp = re.search(r'<meta http-equiv="Content-Security-Policy" content="([^"]+)"', markup)
        if not csp:
            fail(f'{label} has no Content Security Policy')
            continue
        policy = csp.group(1)
        for directive in ("script-src 'self'", "object-src", "default-src 'none'",
                          "base-uri 'none'", "require-trusted-types-for 'script'"):
            if directive.split()[0] not in policy:
                fail(f'{label} — CSP is missing {directive.split()[0]}')
        if "'unsafe-inline'" in policy.split('style-src')[0]:
            fail(f'{label} — CSP allows inline script, which defeats it')
        if "'unsafe-eval'" in policy:
            fail(f'{label} — CSP allows eval')

        handlers = re.findall(r'\son[a-z]+\s*=\s*["\']?[^>\s]', markup)
        if handlers:
            fail(f'{label} carries {len(handlers)} inline event handler(s); '
                 f'they cannot run under this CSP and would need unsafe-inline')

        # Only pages that run JavaScript need the policy installed. The redirect
        # stubs and the blog list carry no script at all, and adding a sanitiser
        # to a page with nothing to sanitise is bytes for the sake of a green
        # tick. The policy has to be there whenever anything else is, though,
        # and it has to come first: deferred scripts run in document order, so
        # the order in the markup is the guarantee.
        scripts = re.findall(r'<script[^>]*\bsrc=["\']?([^"\'\s>]+)', markup)
        if scripts:
            if not any('trusted-types.js' in s for s in scripts):
                fail(f'{label} runs scripts but does not install the Trusted Types policy')
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

    check_robots(out, fail)
    check_security_txt(out, fail)
    check_schedule(out, fail)
    check_live_urls(out, fail)
    check_home_page(out, fail)
    check_speaking(out, fail)

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
