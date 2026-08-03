# Edition cover images

Drop the cover for an edition in here and name it after the edition file, then
point at it from that edition's frontmatter:

```
cover: 001-understand-before-you-apply.jpg
cover_alt: What the image shows, for anyone who cannot see it.
```

The build copies the file next to the rendered page, so it ends up at
`/newsletter/<slug>/<filename>` and the URL cannot drift from the file.

## What a cover changes

Three things, not one:

- it renders at the top of the edition page, under the header
- it becomes that page's `og:image` and `twitter:image`, so a share on
  LinkedIn or Slack previews the edition rather than the site's generic card
- it becomes the `image` field in the page's JSON-LD, which Google uses for
  article rich results

Without a cover the page is unchanged and falls back to `/og-card.png`, which
is what every page on the site used before this existed.

## Size

The LinkedIn originals are 1279x720. Anything 16:9 and at least 1200px wide is
right: that covers the Open Graph recommendation of 1200x630 with room to crop,
and the page displays it at 16:9 regardless.

Dimensions are measured from the file at build time, not declared here, so the
markup always reserves the correct space and the article never jumps down the
page when the image loads. Re-export at a different size and nothing needs
updating.

## cover_alt

Not optional in practice. `verify_build` fails a cover with no `alt` attribute
at all. If the image is purely decorative, set `cover_alt:` to an empty string
deliberately; if it carries meaning, describe it.

## What is checked

The build reports a `cover` that names a file that is not here, and a cover
with no `cover_alt`. `verify_build` refuses to deploy a page whose cover image
or whose `og:image` does not resolve to a file that actually exists in the
build, because a dead share card is invisible from your own site: it only
shows up in someone else's timeline.
