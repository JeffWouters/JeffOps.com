# JeffOps.com

A static site. Markdown in, real HTML pages out, published to GitHub Pages.

The design is a single-page app: one `index.html` with hash routing for Home,
Speaking, Consulting, Training, Projects and the rest. That is fine for those
sections — they are one document and they behave like one.

Blog posts are different. A post needs its own URL so it can be linked to,
shared with a preview card, and indexed. So `build.py` renders every markdown
post to its own page at build time. The SPA still works and still lists the
posts; it just links out to the real pages instead of swapping a div.

## Writing a post

Create a folder, write markdown, done:

```
blog/2026/20260815 - Where AI Belongs in Ops/post.md
```

The folder name carries the date (`YYYYMMDD`) and the year folder groups them.
The first `# Heading` in the file becomes the title.

Frontmatter is optional:

```markdown
---
tags: [ai, ops, automation]
slug: where-ai-belongs-in-ops
description: A one-line summary for search results and preview cards.
series: Practical AI-tomation
---

# Where AI Belongs in Ops

Body text starts here.
```

**`slug` is the one field worth setting deliberately.** It becomes the URL, and
frontmatter wins over the title. That means you can rewrite a headline later
without breaking a link someone already shared. Without it the slug is derived
from the title, and changing the title moves the page.

Everything else is derived: reading time, excerpt, related posts (by shared
tags and series), and the topic and series filters on the blog page.

## Building

```bash
pip install -r requirements.txt
python build.py            # → _site/
python verify_build.py     # checks the build before it ships
```

`_site/` is disposable and gitignored — it is rebuilt from scratch every time.

To preview, build and serve in one step:

```bash
python build.py --serve          # http://localhost:8000/
python build.py --serve 3000     # or pick a port
```

**Opening the output with `file://` does not work, and cannot be made to
work.** Asset paths and links between pages are root-absolute, which is correct
for a deployed site and meaningless on a filesystem: under `file://` a leading
slash resolves to the drive root, so the stylesheet 404s and every link lands
nowhere. Making the assets relative would fix the stylesheet but not the links,
because a directory URL under `file://` shows a directory listing instead of
its `index.html`. Serve it on a port — the same way it will actually be served
in production.

## Deploying

Push to `main`. `.github/workflows/deploy.yml` installs the dependencies, runs
the build, runs the verifier, and publishes `_site/` to GitHub Pages. If the
verifier fails the deploy does not happen.

In the repository settings, Pages must be set to **GitHub Actions** as the
source rather than a branch. The `CNAME` file pointing at `jeffops.com` is
generated into the output, so the custom domain survives every deploy.

## What each file does

`generate_blog_index.py` scans the blog folders and produces the metadata —
`blog/index.json`, `index.js`, `topics.json`, `series.json` — that the SPA
loads. Run on its own it does exactly what it always did.

`build.py` imports that, renders each post to `posts/YYYY/slug/index.html`,
and writes `posts/index.html`, `rss.xml`, `sitemap.xml`, `robots.txt` and an
`og-card.png`. The nav and footer are lifted straight out of `index.html` at
build time, so the design lives in one place and post pages cannot drift from
the rest of the site.

`verify_build.py` is the safety net. Its central check is that the article text
appears as literal text in each page's HTML. That is the failure this whole
architecture exists to prevent, and it is a quiet one: a build can produce
pages that look perfect in a browser while being completely empty to anything
that does not run JavaScript. The check runs in CI and blocks the deploy.

`js/post-page.js` adds syntax highlighting, mermaid diagrams, copy buttons,
the contents sidebar and the reading progress bar to rendered pages. All of it
is enhancement — with JavaScript off, the article still reads fine.

## Known gap

The newsletter subscribe form does not subscribe anyone. `handleSubscribe()`
in `js/app.js` clears the input and displays a confirmation message; it stores
nothing and sends nothing. Every address entered so far is gone. This needs an
actual backend — a form endpoint, an email provider, or a link straight to the
LinkedIn newsletter — before the form is shown to anyone.
