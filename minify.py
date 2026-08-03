#!/usr/bin/env python3
"""Minify a built site in place.

Runs as a separate pipeline step *after* verify_build, never before. Two of the
verifier's guards read things minification destroys: several checks match markup
patterns that whitespace collapsing rearranges, and the TODO(jeff) guard
deliberately searches HTML comments, which are invisible on the page and would
otherwise ship silently. Strip them first and that guard passes forever without
ever looking at anything.

Source files are untouched. The comments in css/styles.css and js/*.js are the
record of why the code is the way it is; they are removed from what is served,
not from what is kept.

Scope is deliberately narrow — .html, .css and .js only. robots.txt,
security.txt and the published index.md files all carry comments written for
whoever reads those files directly, and a minifier has no business in them.

Usage:  python minify.py _site
        python minify.py _site --dry-run
"""

from __future__ import annotations

import argparse
import gzip
import sys
from pathlib import Path

import minify_html
import rcssmin
import rjsmin

# Files the build emits that must not be rewritten even though they match an
# extension above. blog/index.js is generated data, not code: rjsmin would walk
# every post's markdown looking for comment syntax to strip, and a '//' inside
# a URL in someone's prose is not a comment.
SKIP = {'blog/index.js', 'blog/speaking.js'}

# No source map is emitted, because rjsmin cannot produce one and a fabricated
# map is worse than none: `//# sourceURL` would relabel the minified script with
# the original's filename, so devtools would show minified code under a name
# that promises otherwise.
#
# What the pipeline does instead is publish the readable original beside the
# minified file. That is enough here because rjsmin only strips comments and
# whitespace — it never renames anything — so a production stack trace still
# reads "initOrbital is not defined" rather than "t is not a function". The loss
# is line numbers, and app.src.js is one click away for those. A real mappings
# file needs a minifier that generates one; terser does, at the cost of a second
# toolchain in CI.
SOURCE_SUFFIX = '.src.js'


def human(n: int) -> str:
    return f'{n / 1024:.1f} KB'


def gz(data: bytes) -> int:
    return len(gzip.compress(data, 9))


def minify_site(out: Path, dry_run: bool = False) -> int:
    before_raw = before_gz = after_raw = after_gz = 0
    touched = 0

    for path in sorted(out.rglob('*')):
        if not path.is_file():
            continue
        rel = path.relative_to(out).as_posix()
        if rel in SKIP:
            continue
        suffix = path.suffix.lower()
        if suffix not in ('.html', '.css', '.js'):
            continue

        original = path.read_bytes()
        try:
            if suffix == '.css':
                result = rcssmin.cssmin(original)
            elif suffix == '.js':
                result = rjsmin.jsmin(original)
            else:
                # keep_closing_tags and keep_html_and_head_opening_tags keep the
                # document shape a parser — or a regex in a smoke test — expects.
                text = original.decode('utf-8')
                result = minify_html.minify(
                    text, keep_closing_tags=True,
                    keep_html_and_head_opening_tags=True).encode('utf-8')
        except Exception as exc:                      # noqa: BLE001
            print(f'  ! {rel}: {type(exc).__name__}: {exc} — left unminified')
            continue

        # A minifier that grows a file has misunderstood it. Keep the original.
        if len(result) >= len(original):
            continue

        before_raw += len(original)
        after_raw += len(result)
        before_gz += gz(original)
        after_gz += gz(result)
        touched += 1

        if dry_run:
            continue

        if suffix == '.js':
            # Publish the readable original beside the minified file, so a
            # production error can be traced back to real code.
            source_copy = path.with_name(path.stem + SOURCE_SUFFIX)
            source_copy.write_bytes(original)

        path.write_bytes(result)

    print(f'Minified {touched} file(s)')
    print(f'  raw   {human(before_raw)} → {human(after_raw)}  '
          f'(−{human(before_raw - after_raw)})')
    print(f'  gzip  {human(before_gz)} → {human(after_gz)}  '
          f'(−{human(before_gz - after_gz)}), which is what a visitor pays')
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', nargs='?', default='_site')
    parser.add_argument('--dry-run', action='store_true',
                        help='report the saving without writing anything')
    args = parser.parse_args()

    out = Path(args.out)
    if not out.is_dir():
        print(f'No build directory at {out}')
        return 1
    return minify_site(out, args.dry_run)


if __name__ == '__main__':
    sys.exit(main())
