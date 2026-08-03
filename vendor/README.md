# vendor/

Third-party code and fonts, committed rather than fetched from a CDN.

Nothing here is edited. Each file is the published artefact at the version
named below, copied from npm, with its licence beside it.

| file | package | version | licence |
|---|---|---|---|
| `highlight.min.js` | `@highlightjs/cdn-assets` | 11.9.0 | BSD-3-Clause |
| `github-dark.min.css` | `@highlightjs/cdn-assets` | 11.9.0 | BSD-3-Clause |
| `marked.min.js` | `marked` | 9.1.6 | MIT |
| `fonts/inter-latin-*.woff2` | `@fontsource/inter` | latin subset | OFL-1.1 |
| `fonts/jetbrains-mono-latin-*.woff2` | `@fontsource/jetbrains-mono` | latin subset | OFL-1.1 |

## Why these are here rather than on a CDN

Browsers partitioned their HTTP cache by top-level site in 2020. A visitor's
copy of a library fetched on someone else's site is no longer reused here, so
the old argument for a shared CDN no longer holds: what is left is two extra
DNS lookups and two extra TLS handshakes before anything renders.

The fonts had a second cost. `fonts.googleapis.com` served a stylesheet that
named files on `fonts.gstatic.com`, so the browser could not start fetching a
font until it had fetched and parsed that stylesheet — two round trips, in
series, on the critical path. Self-hosting removes both, and stops handing
every visitor's IP address to Google, which for a commercial site with EU
readers is worth more than the bytes.

## Updating

Reinstall the package, copy the file, copy its licence, and check the version
in the table. There is no automatic update, which is deliberate: a silent
upgrade of a script that runs on every page is not something a static site
should do to itself.

```
npm install @highlightjs/cdn-assets@<version>
cp node_modules/@highlightjs/cdn-assets/highlight.min.js vendor/
```

## What is not here

Mermaid is not vendored. It is 2.9 MB (875 KB gzipped) — larger than the rest
of the site put together — and no post currently contains a diagram. It is
loaded from a CDN on demand, by the page, only once a `mermaid` code block is
actually found. Today that never happens and nothing is fetched.
