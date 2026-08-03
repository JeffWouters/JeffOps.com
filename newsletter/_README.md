# Newsletter editions

One folder per edition of The JeffOps Dispatch, named `NNN-slug`, containing
`edition.md` and any images that edition uses. Folders starting with an
underscore are ignored by the build; this file is one.

```
newsletter/
  001-understand-before-you-apply/
    edition.md
    cover.jpg
  002-why-ai-works-for-coding/
    edition.md
```

A folder rather than a loose file so an edition's pictures live with the words
that use them. A shared image directory works right up until you want to know
which of forty files still matters, or you delete an edition and leave its
artwork behind forever. It is also how blog posts already work.

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
cover: cover.jpg
cover_alt: What the image shows, for anyone who cannot see it.
---
```

`slug` is the contract with the outside world. Once an edition is live,
changing it breaks every link to it, so pick it once and leave it alone.
`description` is optional: with none, the build takes the opening of the body.
`cover` and `cover_alt` are optional too.

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

## Images

Every file in the folder that is not markdown is copied next to the rendered
page, so a relative `![alt](picture.png)` in the body resolves both on the
static page and in the single-page app. Nothing to think about beyond dropping
the file in the folder.

The `cover` is the one image with a job beyond the page. It renders at the top
under the header, it becomes that page's `og:image` and `twitter:image`, and it
becomes the `image` field in the page's JSON-LD, which Google uses for article
rich results. Without one the page falls back to the site's generic
`/og-card.png`, which is what every page used before this existed.

Size: the LinkedIn originals are 1279x720. Anything 16:9 and at least 1200px
wide is right. Dimensions are measured from the file at build time, not
declared in frontmatter, so the markup always reserves the correct space and
the article never jumps down the page as the image loads. Re-export at a
different size and nothing needs updating.

`cover_alt` is not optional in practice: `verify_build` fails a cover with no
`alt` attribute at all. If the image is purely decorative, set it to an empty
string deliberately; if it carries meaning, describe it.

## What the build guarantees

`verify_build.py` refuses to deploy an edition page that does not say where the
edition was first published, does not link to the LinkedIn original, is not
canonical to its own URL on this site, still carries the `TODO(jeff)` marker,
or has under 150 words of body text. That last one catches the case where a
paste went wrong and left a page that looks published but is nearly empty.

It also refuses a page whose cover image or whose `og:image` does not resolve
to a file that exists in the build. A dead share card is invisible from your
own site; it only shows up in someone else's timeline.

The build reports, at build time, an edition with no `linkedin_url`, a `cover`
naming a file that is not in the edition's folder, and a cover with no
`cover_alt`.

## Canonical

Each edition page is canonical to itself on jeffops.com, not to LinkedIn. Jeff
owns the writing, and the copy that should rank is the one on his own site.
LinkedIn's copy stays up and is linked from the page.
