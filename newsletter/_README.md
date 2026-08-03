# Newsletter editions

One markdown file per edition of The JeffOps Dispatch, named `NNN-slug.md`.
Files starting with an underscore, like this one, are ignored by the build.

Editions are published on LinkedIn first and republished here. The frontmatter
is the record of the edition; the body is the copy of it.

## Frontmatter

```
---
number: 4
title: The title exactly as published
date: 2026-08-03
slug: url-slug
linkedin_url: https://www.linkedin.com/pulse/...
description: One or two sentences for search results and preview cards.
---
```

`slug` is the contract with the outside world. Once an edition is live, changing
it breaks every link to it, so pick it once and leave it alone. `description` is
optional: with none, the build takes the opening of the body instead.

## Publishing an edition here

Paste the edition text below the frontmatter, as markdown, and delete the
`TODO(jeff)` line. That is the whole step.

Until a body exists, the edition is not missing and the build does not fail. It
keeps its place in the archive on the site, its entry is marked `on LinkedIn`
and links there, and it appears nowhere else. Add the body and the same edition
gets its own page at `/newsletter/<slug>/`, its archive entry switches to that
page, and it joins the blog index, the RSS feed and the sitemap.

So a half-migrated archive is a normal state, and nothing empty can reach the
site by accident.

## What the build guarantees

`verify_build.py` refuses to deploy an edition page that does not say where the
edition was first published, does not link to the LinkedIn original, is not
canonical to its own URL on this site, still carries the `TODO(jeff)` marker, or
has under 150 words of body text. That last one catches the case where a paste
went wrong and left a page that looks published but is nearly empty.

The origin note is generated from `linkedin_url`, so an edition with no
`linkedin_url` in its frontmatter is reported at build time.

## Canonical

Each edition page is canonical to itself on jeffops.com, not to LinkedIn. Jeff
owns the writing, and the copy that should rank is the one on his own site.
LinkedIn's copy stays up and is linked from the page.
