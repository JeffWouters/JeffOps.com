#!/usr/bin/env bash
#
# Check that the deployed site actually serves what the build produced.
#
# This exists because of a real failure. upload-pages-artifact strips dotfiles
# unless told otherwise, so /.well-known/ never reached production while the
# build, the verifier and the deploy all reported success. Nothing in CI looks
# at the deployed site, so the only thing standing between that bug and
# forever was somebody thinking to check by hand.
#
# Everything here is checked over HTTP against the live origin, after the
# deploy. That is the only place this class of bug is visible.
#
# Usage:  tools/smoke_test.sh [base-url]     (default https://jeffops.com)

set -uo pipefail

SITE="${1:-https://jeffops.com}"
ATTEMPTS="${SMOKE_ATTEMPTS:-10}"
PAUSE="${SMOKE_PAUSE:-15}"

failures=0
workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

# A Pages deploy is not instant at the edge, so a single miss proves nothing.
# Retry before believing a failure, and fail hard once the retries are spent.
fetch() {
    local path="$1" dest="$2" attempt=1
    while :; do
        if curl -fsSL --max-time 20 "$SITE$path" -o "$dest" 2>/dev/null; then
            return 0
        fi
        [ "$attempt" -ge "$ATTEMPTS" ] && return 1
        attempt=$((attempt + 1))
        sleep "$PAUSE"
    done
}

# A 200 is not enough. GitHub Pages answers a missing path with a styled 404
# page, and a redirect stub is also a 200 with the wrong body, so every check
# asserts something that can only be in the real file.
check() {
    local path="$1" needle="$2" dest
    dest="$workdir/$(printf '%s' "$path" | tr -c 'a-zA-Z0-9' '_')"
    if ! fetch "$path" "$dest"; then
        printf '  FAIL  %s is not served (still failing after %s attempts)\n' "$path" "$ATTEMPTS"
        failures=$((failures + 1))
        return 1
    fi
    if ! grep -qF -- "$needle" "$dest"; then
        printf '  FAIL  %s is served but does not contain %s\n' "$path" "$needle"
        failures=$((failures + 1))
        return 1
    fi
    printf '  ok    %s\n' "$path"
    return 0
}

printf 'Smoke-testing %s\n\n' "$SITE"

# The one that actually broke. RFC 9116 names /.well-known/security.txt as the
# location; the root copy is a fallback, so a scanner following the spec sees
# only the first. It is checked first because it is the canary for the whole
# dotfile-stripping problem.
check /.well-known/security.txt 'Contact:'
check /security.txt             'Contact:'

check /                'JeffOps'
check /robots.txt      'Sitemap: '
check /sitemap.xml     '<urlset'
check /rss.xml         '<rss'
check /posts/          'Blog'

# .nojekyll is the other dotfile, and it is what stops Pages running Jekyll and
# discarding anything whose name begins with an underscore. It is empty, so
# there is nothing to grep: a 200 is the whole test.
if fetch /.nojekyll "$workdir/nojekyll"; then
    printf '  ok    /.nojekyll\n'
else
    printf '  FAIL  /.nojekyll is not served, so Pages may be running Jekyll\n'
    failures=$((failures + 1))
fi

# The two security.txt copies are byte-identical in the build, and the verifier
# enforces that. Proving it again live catches a deploy that rewrote or
# truncated one of them, which would leave two files disagreeing about who to
# contact and which one to trust.
if [ -s "$workdir/__well_known_security_txt" ] && [ -s "$workdir/_security_txt" ]; then
    if cmp -s "$workdir/__well_known_security_txt" "$workdir/_security_txt"; then
        printf '  ok    both security.txt copies are identical\n'
    else
        printf '  FAIL  the two security.txt copies differ in production\n'
        failures=$((failures + 1))
    fi
fi

printf '\n'
if [ "$failures" -gt 0 ]; then
    printf '%s check(s) failed. The deploy reported success but the site is not serving what was built.\n' "$failures"
    exit 1
fi
printf 'All checks passed.\n'
