# Vendored front-end assets

The panel's `base.html` previously loaded these from `cdn.jsdelivr.net` /
`unpkg.com` — vendored here instead so the panel works fully offline
(no CDN dependency at request time, not just at `docker build` time) and
so it doesn't break if either CDN is ever unreachable.

| File | Package | Pinned version |
|---|---|---|
| `pico.min.css` | [`@picocss/pico`](https://picocss.com/) | 2.1.1 |
| `htmx.min.js` | [`htmx.org`](https://htmx.org/) | 1.9.12 |
| `alpine.min.js` | [`alpinejs`](https://alpinejs.dev/) | 3.16.3 (previously loaded as the floating range `3.x.x` — pinning here also makes the version reproducible, not just offline) |

## Refreshing

Each is a single pre-built file with no build step — to bump a version,
just re-download the same URL pattern with the new version number and
replace the file here:

```sh
curl -sSL "https://cdn.jsdelivr.net/npm/@picocss/pico@<version>/css/pico.min.css" -o pico.min.css
curl -sSL "https://unpkg.com/htmx.org@<version>/dist/htmx.min.js" -o htmx.min.js
curl -sSL "https://unpkg.com/alpinejs@<version>/dist/cdn.min.js" -o alpine.min.js
```
