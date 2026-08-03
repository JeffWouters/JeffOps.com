from pathlib import Path
from datetime import datetime, timezone
import json
import re

FRONTMATTER_RE = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.DOTALL)
DEFAULT_MARKDOWN_NAMES = ['post.md', 'index.md', 'README.md']
DEFAULT_RELATED_COUNT = 3

ROOT = Path(__file__).resolve().parent
BLOG_DIR = ROOT / 'blog'
OUTPUT_FILE = BLOG_DIR / 'index.json'
JS_OUTPUT_FILE = BLOG_DIR / 'index.js'

if not BLOG_DIR.exists():
    raise SystemExit('Missing blog directory: blog/')


def strip_frontmatter(text):
    match = FRONTMATTER_RE.match(text)
    return text[match.end():] if match else text


# 'number' and 'linkedin_url' are only meaningful on newsletter editions, but the
# parser is shared. A key absent from this tuple is silently dropped, which is how
# every edition came through with no LinkedIn URL and nothing to credit.
SCALAR_FRONTMATTER_KEYS = ('series', 'slug', 'canonical', 'description', 'title', 'date',
                           'reviewed', 'author', 'draft', 'number', 'linkedin_url',
                           'cover', 'cover_alt')



# ── Publication schedule ──────────────────────────────────────────────
#
# A post is published when its date has arrived, and is invisible before that:
# no page, no URL, no index entry, no feed item, no sitemap line, and no copy of
# its markdown in the output. "Not listed" is not the same as "not published",
# and only the second one is safe.
#
# The date comes from frontmatter if present and from the folder name otherwise,
# so an existing post needs no change. A time may be given for same-day control;
# a bare date means midnight. Everything is treated as UTC, because that is the
# clock the build runs on and a build cannot know anything else.
#
# One deliberate asymmetry: a post whose date cannot be parsed at all is
# published rather than withheld. Withholding it would make a post silently
# vanish because of a typo, and a silent disappearance is worse than an early
# appearance you can see.

DATE_FORMATS = ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%d %H:%M', '%Y-%m-%d', '%Y/%m/%d')

TRUTHY = ('true', 'yes', 'y', '1', 'on')

# Dates without an explicit offset are read as Amsterdam local time, because
# that is the clock the author writes against. "date: 2026-08-17" means midnight
# on the 17th in Amsterdam, which is 22:00 UTC on the 16th in summer and 23:00
# in winter. Reading it as UTC instead would put the post live the previous
# evening, which is the kind of thing you only notice once.
SITE_TZ_NAME = 'Europe/Amsterdam'
try:
    from zoneinfo import ZoneInfo
    SITE_TZ = ZoneInfo(SITE_TZ_NAME)
except Exception:                                    # pragma: no cover
    # Falling back silently would shift every publication by an hour or two with
    # nothing on screen to explain it, so say so loudly instead.
    print(f'WARNING: no timezone database for {SITE_TZ_NAME}; dates without an '
          f'offset will be read as UTC. Install the "tzdata" package to fix this.')
    SITE_TZ = timezone.utc


def as_utc(dt):
    """Attach the site timezone to a naive datetime, then normalise to UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=SITE_TZ)
    return dt.astimezone(timezone.utc)


def in_site_tz(dt):
    return dt.astimezone(SITE_TZ)


def utc_now():
    return datetime.now(timezone.utc)


def parse_publish_value(value):
    """Parse a frontmatter date into an aware UTC datetime, or None."""
    if not value:
        return None
    text = str(value).strip().strip('"\'')
    if not text:
        return None
    normalised = text[:-1] + '+00:00' if text.endswith(('Z', 'z')) else text
    try:
        return as_utc(datetime.fromisoformat(normalised))
    except ValueError:
        pass
    for fmt in DATE_FORMATS:
        try:
            return as_utc(datetime.strptime(text, fmt))
        except ValueError:
            continue
    return None


def resolve_publish(frontmatter, folder_name):
    """Return (datetime, confident). Confidence gates whether we may withhold."""
    from_front = parse_publish_value(frontmatter.get('date'))
    if from_front:
        return from_front, True
    m = re.match(r'^(\d{4})(\d{2})(\d{2})', folder_name)
    if m:
        try:
            return as_utc(datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))), True
        except ValueError:
            pass
    return utc_now(), False


def is_draft(frontmatter):
    return str(frontmatter.get('draft', '')).strip().lower() in TRUTHY


def parse_frontmatter(text):
    frontmatter = {}
    match = FRONTMATTER_RE.match(text)
    if not match:
        return frontmatter
    for line in match.group(1).splitlines():
        if ':' not in line:
            continue
        key, value = line.split(':', 1)
        key = key.strip()
        value = value.strip()
        if key == 'tags':
            if value.startswith('[') and value.endswith(']'):
                raw_tags = [item.strip().strip('"\'\'') for item in value[1:-1].split(',')]
                frontmatter['tags'] = [slugify(tag) for tag in raw_tags if tag]
        elif key in SCALAR_FRONTMATTER_KEYS:
            frontmatter[key] = value.strip().strip('"\'\'')
    return frontmatter


def strip_leading_h1(text):
    """Remove the leading '# Title' line — the page template renders the title itself."""
    lines = strip_frontmatter(text).lstrip().splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith('# '):
            return '\n'.join(lines[i + 1:]).lstrip('\n')
        if line.strip():
            break
    return '\n'.join(lines)


def slugify(text):
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-') if text else ''



def derive_tags(text, known_tags):
    if not known_tags:
        return []
    content = strip_frontmatter(text).lower()
    tags = []
    for tag in known_tags:
        keyword = tag.replace('-', ' ').replace('/', ' ').lower()
        if re.search(r'\b' + re.escape(keyword) + r'\b', content):
            tags.append(tag)
    return tags


def parse_title(text, default):
    text = strip_frontmatter(text)
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('# '):
            return line[2:].strip()
    return default


def find_markdown_file(directory, candidate_names=None):
    candidate_names = candidate_names or DEFAULT_MARKDOWN_NAMES
    for name in candidate_names:
        candidate_path = directory / name
        if candidate_path.exists():
            return candidate_path
    markdown_files = sorted(directory.glob('*.md'))
    return markdown_files[0] if markdown_files else None


def parse_excerpt(text):
    text = strip_frontmatter(text)
    lines = [line.strip() for line in text.splitlines()]
    excerpt_lines = []
    in_code = False
    for line in lines:
        if line.startswith('```'):
            in_code = not in_code
            continue
        if in_code or not line or line.startswith('#'):
            continue
        excerpt_lines.append(line)
        if len(excerpt_lines) >= 2:
            break
    excerpt = ' '.join(excerpt_lines).strip()
    excerpt = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', excerpt)
    excerpt = re.sub(r'\*\*(.*?)\*\*', r'\1', excerpt)
    excerpt = re.sub(r'\*(.*?)\*', r'\1', excerpt)
    excerpt = excerpt[:220].rstrip()
    return excerpt



def reviewed_iso(frontmatter, published_iso):
    """ISO date the post was last reviewed, falling back to its publish date.

    A `reviewed:` line in the frontmatter that cannot be parsed is ignored rather
    than guessed at — a wrong review date is worse than none, because it claims
    a check that never happened.
    """
    parsed = parse_publish_value(frontmatter.get('reviewed'))
    if not parsed:
        return published_iso
    # Back into site time before dropping the offset, the same way the publish
    # date is handled. Formatting the UTC value instead turns a review dated the
    # 20th into the 19th for half the year, which is a lie about a date whose
    # entire job is to be trusted.
    return in_site_tz(parsed).replace(tzinfo=None).isoformat()


def reviewed_label(frontmatter):
    parsed = parse_publish_value(frontmatter.get('reviewed'))
    return in_site_tz(parsed).strftime('%b %d, %Y') if parsed else ''


def estimate_readtime(text):
    words = len(re.findall(r'\w+', text))
    return f'{max(1, round(words / 200))} min read'


def display_label_for_tag(tag):
    words = re.split(r'[-_/ ]+', tag)
    parts = []
    for word in words:
        if not word:
            continue
        if len(word) <= 3:
            parts.append(word.upper())
        else:
            parts.append(word.capitalize())
    return ' '.join(parts)


def build_topics(posts):
    counts = {}
    for item in posts:
        for tag in item.get('tags', []):
            counts[tag] = counts.get(tag, 0) + 1
    topics = [
        {'key': tag, 'label': display_label_for_tag(tag), 'count': count}
        for tag, count in counts.items()
    ]
    topics.sort(key=lambda item: (-item['count'], item['label']))
    return topics


def build_series(posts):
    counts = {}
    labels = {}
    for item in posts:
        series_key = item.get('series', '')
        series_label = item.get('series_label', '')
        if not series_key:
            continue
        counts[series_key] = counts.get(series_key, 0) + 1
        labels[series_key] = series_label or labels.get(series_key, series_key)
    series = [
        {'key': key, 'label': labels[key], 'count': count}
        for key, count in counts.items()
    ]
    series.sort(key=lambda item: (-item['count'], item['label']))
    return series


def calculate_related_posts(posts, max_related=3):
    for item in posts:
        scores = []
        item_tags = set(item.get('tags', []))
        item_series = item.get('series', '')
        for candidate in posts:
            if candidate['folder'] == item['folder']:
                continue
            score = 0
            candidate_tags = set(candidate.get('tags', []))
            shared_tags = item_tags.intersection(candidate_tags)
            score += len(shared_tags) * 10
            if item_series and item_series == candidate.get('series', ''):
                score += 30
            elif item_series and candidate.get('series', ''):
                score += 5
            if score > 0:
                scores.append((score, candidate['folder']))
        scores.sort(key=lambda entry: (-entry[0], entry[1]))
        item['related'] = [folder for score, folder in scores[:max_related]]
    return posts


TOPICS_FILE = BLOG_DIR / 'topics.json'
SERIES_FILE = BLOG_DIR / 'series.json'


def collect_posts(include_unpublished=False, now=None):
    """Scan blog/YYYY/YYYYMMDD - Title/ folders and return post records, newest first.

    Each record carries everything both the client-side index and the static page
    renderer need. 'markdown' keeps the original body including its H1 (the SPA
    relies on that); 'body_markdown' has the H1 removed for templates that render
    the title themselves.

    Scheduled and draft posts are filtered out here rather than at each point of
    use. Everything downstream reads from this one list: the pages, the client
    index, the RSS feed, the sitemap and the verifier. Filtering once means a
    future post cannot leak through a consumer somebody forgot to update.
    """
    now = now or utc_now()
    posts = []
    for year_dir in sorted([d for d in BLOG_DIR.iterdir() if d.is_dir() and d.name.isdigit()], reverse=True):
        for post_dir in sorted([d for d in year_dir.iterdir() if d.is_dir()]):
            folder = post_dir.relative_to(ROOT).as_posix()
            post_file = find_markdown_file(post_dir)
            if not post_file:
                print(f'Skipping {folder}: no markdown file found')
                continue

            text = post_file.read_text(encoding='utf-8')
            frontmatter = parse_frontmatter(text)
            title = frontmatter.get('title') or parse_title(text, post_dir.name)
            excerpt = parse_excerpt(text)

            published_at, confident = resolve_publish(frontmatter, post_dir.name)
            draft = is_draft(frontmatter)
            scheduled = confident and published_at > now
            published = not draft and not scheduled
            if not published and not include_unpublished:
                continue

            # Display and sort dates read in local time, or a post published at
            # midnight local would show yesterday's date on its own page.
            local = in_site_tz(published_at)
            dt = {'formatted': local.strftime('%b %d, %Y'),
                  'iso': local.replace(tzinfo=None).isoformat()}
            readtime = estimate_readtime(text)
            tags = frontmatter.get('tags') or []
            series_label = frontmatter.get('series', '').strip()
            series_key = slugify(series_label) if series_label else ''
            markdown = strip_frontmatter(text).strip()

            # The slug is the contract with the outside world. Frontmatter wins so
            # that an already-published URL can never be broken by an edit to the
            # title or the folder name.
            slug = frontmatter.get('slug') or slugify(title)
            year = year_dir.name
            url = f'/posts/{year}/{slug}/'

            posts.append({
                'folder': folder,
                'title': title,
                'date': dt['formatted'],
                'readtime': readtime,
                'tags': tags,
                'series': series_key,
                'series_label': series_label,
                'excerpt': excerpt,
                'markdown': markdown,
                'slug': slug,
                'year': year,
                'url': url,
                'iso': dt['iso'],
                # When the post was last checked over, as opposed to when it was
                # first published. Technical writing goes stale silently; this is
                # the field that lets a page admit its own age. Absent means the
                # post has not been revisited, so the publish date stands in.
                'reviewed': reviewed_iso(frontmatter, dt['iso']),
                'reviewed_label': reviewed_label(frontmatter),
                'description': frontmatter.get('description', '') or excerpt,
                'canonical': frontmatter.get('canonical', ''),
                'body_markdown': strip_leading_h1(text).strip(),
                'published_at': published_at.isoformat(),
                'is_draft': draft,
                'is_scheduled': scheduled,
                'is_published': published,
                '_sortDate': dt['iso'],
                '_text': text,
            })

    known_tags = sorted({tag for item in posts for tag in item['tags']})
    for item in posts:
        if not item['tags']:
            item['tags'] = derive_tags(item['_text'], known_tags)
        item.pop('_text', None)

    posts.sort(key=lambda item: item['_sortDate'], reverse=True)
    for item in posts:
        item.pop('_sortDate', None)
    calculate_related_posts(posts, DEFAULT_RELATED_COUNT)
    return posts


# Fields the browser-side index does not need. Dropping them keeps index.js small.
_INDEX_ONLY_DROP = ('body_markdown',)


def write_index_files(posts):
    payload = [{k: v for k, v in item.items() if k not in _INDEX_ONLY_DROP} for item in posts]
    OUTPUT_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
    JS_OUTPUT_FILE.write_text('window._blogIndexData = ' + json.dumps(payload, ensure_ascii=False) + ';', encoding='utf-8')
    TOPICS_FILE.write_text(json.dumps(build_topics(posts), indent=2, ensure_ascii=False), encoding='utf-8')
    SERIES_FILE.write_text(json.dumps(build_series(posts), indent=2, ensure_ascii=False), encoding='utf-8')

    print(f'Generated {len(posts)} blog index entries in {OUTPUT_FILE}')
    print(f'Generated {TOPICS_FILE.name} with {len(build_topics(posts))} topics')
    print(f'Generated {SERIES_FILE.name} with {len(build_series(posts))} series entries')
    return posts


def build_index():
    return write_index_files(collect_posts())


if __name__ == '__main__':
    build_index()


def unpublished_posts(now=None):
    """Posts that exist in the tree but must not reach the site yet."""
    return [p for p in collect_posts(include_unpublished=True, now=now)
            if not p['is_published']]
