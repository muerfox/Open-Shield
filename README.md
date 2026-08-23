# Open-Shield

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Docker Compose](https://img.shields.io/badge/deploy-docker%20compose-2496ED?logo=docker&logoColor=white)](docker-compose.yml)

**Your own Cloudflare, running on your own box.** A self-hosted DNS + CDN +
WAF platform with a Python admin panel — point your domains at it, and get
authoritative DNS, a caching reverse-proxy edge, and a real WAF (block by
IP/CIDR, or by header/URL/body pattern) without handing your traffic to a
third party. Ships as five Docker images and a `docker-compose.yml`; nothing
to install on the host beyond Docker itself.

Built because "self-hosted ingress + WAF + DNS" for a small VPS or home
server shouldn't require stitching together five different dashboards — one
panel, one `docker compose up`, and config changes go live **instantly, with
no reload**, because the whole edge reads its config from Redis on every
request.

## Features

- 🌐 **Real DNS** — [PowerDNS](https://www.powerdns.com/) under the hood, driven entirely through the panel. Zones, A/AAAA/CNAME/MX/TXT/NS/SRV/CAA records.
- 🚀 **CDN** — reverse proxy + caching per domain, powered by [OpenResty](https://openresty.org/). Point it at any origin, anywhere.
- 🃏 **Wildcard domains** — `*.example.com` in one entry, for services that mint a subdomain per user/tenant. Each matching subdomain still gets its own real Let's Encrypt certificate automatically.
- 🛡️ **WAF** — block by IP/CIDR, or by rule: match a header, the URL, or the request body, with `contains`/`regex`/`exact` matching and block-or-log actions. Plus per-domain rate limiting.
- ⚡ **Zero-reload config** — the panel pushes every change straight to Redis; OpenResty's Lua reads it on the next request. No nginx reload, ever, for a domain/rule/IP change.
- 🔒 **Three HTTPS modes per domain** — plain HTTP (no cert hassle), automatic Let's Encrypt, or paste your own certificate.
- 🖥️ **Ingress mode** — run it as the public front door on a real server: real client IPs, `proxy_pass` straight to anything else you've published to `127.0.0.1` on the same box.
- 🔐 **Brute-force-hardened login** — escalating lockout (doubling up to 24h) on the panel itself.
- 📴 **Builds offline** — every Python/Lua dependency is vendored and hash-verified; `docker build` never touches PyPI, GitHub, or luarocks.org.
- 📊 **Live dashboard** — recent WAF events, block counts, all polling live via HTMX.
- 🎨 **Branded error pages** — WAF blocks, rate limits, unknown domains, and origin-down errors all get a custom dark-themed Open-Shield page (never a real origin's own 4xx/5xx, which always pass through untouched).

## Quick start

```sh
git clone git@github.com:muerfox/Open-Shield.git
cd Open-Shield
cp .env.example .env
# edit .env: set real passwords/secrets, PDNS_DEFAULT_NS, EDGE_PUBLIC_HOST, ACME_EMAIL

docker compose up --build
```

Open `https://localhost:8080` and log in with `ADMIN_EMAIL` / `ADMIN_PASSWORD`
from your `.env`. The panel serves HTTPS with a self-signed certificate
(see [Panel login security](#panel-login-security)) — your browser will
warn about that on first visit; click through it (or add an exception).

To try it against a local test backend instead of a real domain:

```sh
docker compose --profile demo up --build
```

This also starts a `demo-origin` (traefik/whoami) container published to
`127.0.0.1:8081` — add a domain in the panel with origin host `127.0.0.1`,
origin port `8081` to test against it.

### Typical first steps in the panel

1. **Domains** → *Add domain*: point it at your real origin (host/port),
   leave "Proxy through Open-Shield" and "Enable WAF" checked, and pick an
   HTTPS mode (see below — **Off** is the default and needs nothing extra).
2. **DNS** → open the new domain's zone, add any extra records you need
   (MX, TXT, etc). The apex `A` record is managed automatically while
   proxying is on.
3. If using HTTPS, point your domain's nameservers at this server
   (`PDNS_DEFAULT_NS`) so PowerDNS actually serves it, and so Let's
   Encrypt's HTTP-01 challenge can reach the edge on port 80.
4. **WAF** → add a rule (e.g. block requests where the `User-Agent` header
   *contains* `sqlmap`) or block a specific IP/CIDR.
5. **Logs** → watch blocked/logged requests roll in live.

## Architecture

| Component  | What it is | Role |
|---|---|---|
| `panel`     | FastAPI + Jinja2/HTMX (Python) | The admin UI: manage domains, DNS records, WAF rules, IP blocks, view logs |
| `openresty` | OpenResty (nginx + Lua) | The public edge on 80/443: reverse proxy, cache, WAF enforcement, automatic HTTPS |
| `powerdns`  | PowerDNS (`pschiffe/pdns-pgsql`) | Real authoritative DNS server for your zones, driven by the panel via its HTTP API |
| `postgres`  | Postgres 16 | Storage for the panel's own config (domains/rules) and for PowerDNS's zone data |
| `redis`     | Redis 7 | Hot-path shared state: domain routing table, WAF rules, IP blocklists, rate-limit counters, ACME cert storage, recent WAF event feed |

**Data flow:** the panel is the source of truth in Postgres for CDN/WAF
config, and pushes a flattened copy into Redis on every change — that's what
OpenResty's Lua modules read on the request hot path, so rule/domain changes
take effect immediately with **no nginx reload**. PowerDNS is the source of
truth for actual DNS records (queried live via its API). When a domain has
"proxy" enabled in the panel, its DNS A record is automatically pointed at
the OpenResty edge (the "orange cloud" mechanic) while the real origin is
kept separately for OpenResty to connect to.

## Deploying on a real server (ingress mode)

`openresty` runs with `network_mode: host` (Linux-only), which does two
things at once:

- It binds ports 80/443 directly on the server's real network interfaces,
  with no Docker NAT in the path — `$remote_addr` in nginx (and so the
  panel's dashboard/log feed) is the genuine client IP.
- `127.0.0.1` inside that container is the **host's real loopback**, so it
  can `proxy_pass` straight to anything you've published to
  `127.0.0.1:<port>` on the same machine — your other apps/containers, not
  just ones in this compose project.

So to front an existing app running elsewhere on the same server: publish
its port to the host's loopback (e.g. another compose project with
`ports: ["127.0.0.1:3000:3000"]`, or a bare process listening on
`127.0.0.1:3000`), then in the Open-Shield panel add a domain with
origin host `127.0.0.1`, origin port `3000`.

Everything else in the stack (`postgres`, `redis`, `powerdns`, `panel`)
stays on the isolated `openshield` bridge network as before — `redis` and
`panel` additionally publish loopback-only ports so the now-host-networked
`openresty` can still reach them.

Trade-off worth knowing: host networking removes network isolation for
that one container — it can reach (and be reached by) anything else
listening on the host's network stack, not just what you intend it to. If
you don't need the `127.0.0.1`-origin use case, you can revert `openresty`
to normal bridge networking (add back `ports: ["80:80", "443:443"]` and
`networks: [openshield]`, remove `network_mode: host`, and point
`REDIS_URL` back at `redis:6379`) — real client IPs still work fine in
that mode too for genuine external traffic (Docker's port-publishing DNAT
preserves the original source IP; it's only requests originating from the
host itself, like `curl localhost`, that show up as the bridge gateway IP,
which is expected and not a real-world concern).

### Start on boot

1. Make sure the Docker daemon itself is enabled: `sudo systemctl enable --now docker`.
   Combined with `restart: unless-stopped` on every service, that alone is
   enough to bring the stack back after a reboot **as long as it was
   running (not manually `docker compose down`'d) beforehand**.
2. For a fully deterministic boot regardless of prior state, install the
   provided systemd unit instead:

   ```sh
   sudo cp deploy/open-shield.service /etc/systemd/system/
   sudo sed -i "s#/opt/open-shield#$(pwd)#" /etc/systemd/system/open-shield.service
   sudo systemctl daemon-reload
   sudo systemctl enable --now open-shield.service
   ```

   This runs `docker compose up -d` on boot and `docker compose down` on
   `systemctl stop open-shield` — use `systemctl {start,stop,restart,status}
   open-shield` instead of `docker compose` directly once it's installed.

## HTTPS modes

Each domain has its own **HTTPS** setting on the domain form:

- **Off** (default) — served over plain HTTP only, port 80, no redirect to
  HTTPS. No DNS/ACME/certificate setup required — this is the easiest way to
  get a domain (or `demo-origin` for local testing) working end-to-end
  through the CDN/WAF immediately.
- **Automatic** — the existing Let's Encrypt flow via `lua-resty-auto-ssl`.
  Requires `EDGE_PUBLIC_HOST` set, the domain's DNS actually pointed at this
  server, port 80 reachable from the public internet for the ACME HTTP-01
  challenge, and a real contact email set on the panel's **Settings** page
  (not on a domain like `example.com`/`.net`/`.org` — Let's Encrypt rejects
  those with an `invalidContact` error). Settings changes take effect within
  about a minute, no restart needed. A failed issuance attempt backs off
  for 2 minutes before retrying (rather than retrying — and blocking — on
  every single request), so a still-broken DNS/firewall setup won't also
  make the site slow while you fix it.
- **Manual** — paste your own certificate (PEM, full chain) and private key
  (PEM) directly into the domain form. OpenResty picks it up on the next TLS
  handshake — no reload needed. Leave both boxes blank on an edit to keep
  the currently stored cert.

Domains with HTTPS on ("automatic" or "manual") get all plain-HTTP traffic
301-redirected to HTTPS; domains with HTTPS "off" are served on port 80 only
(hitting port 443 for one of these still works — the WAF/routing pipeline
runs the same way — but you'll get a browser certificate warning, since only
the edge's self-signed fallback cert is presented).

## Wildcard domains

Add `*.example.com` as a domain name (instead of a specific subdomain) to
match *any* subdomain that doesn't already have its own exact entry —
built for services that mint a subdomain per user/tenant. One entry
handles all of them:

- **Origin/cache/rate-limit config** is shared across every matching
  subdomain — the origin app is expected to look at the `Host` header
  itself to figure out which tenant it's serving (the standard pattern for
  this kind of setup). Rate limiting is still tracked *per subdomain*
  though, so one noisy tenant doesn't eat another's quota.
- **WAF rules and IP/CIDR blocks** scoped to the wildcard domain in the
  panel apply to every subdomain under it.
- **DNS**: the panel creates a single `*.example.com` A record (in the
  `example.com` zone) pointed at the edge — that one record makes every
  subdomain resolve here, no DNS changes needed as new subdomains appear.
- **HTTPS**: with mode set to **Automatic**, each subdomain gets issued
  its own real Let's Encrypt certificate the first time it's actually
  visited (HTTP-01 validates concrete hostnames fine — it just can't issue
  the `*.` pattern itself — so this isn't a true wildcard cert, it's a
  real one per subdomain, which needs no special ACME DNS-01 setup and
  works out of the box). **Manual** mode works too, if you already have an
  actual wildcard certificate from elsewhere (DNS-01 via another tool, or
  purchased) — paste it once and it covers every subdomain.

Only one level of wildcard is supported (`*.example.com` matches
`foo.example.com`, not `foo.bar.example.com`), and an exact entry for a
specific subdomain always takes priority over a wildcard if both exist.

## Panel login security

**HTTPS by default.** uvicorn terminates TLS directly with a self-signed
certificate generated fresh at `docker build` time (100-year validity,
`panel/Dockerfile`) — a unique key per build, never committed to the repo.
The session cookie is also marked `Secure`. This encrypts the connection
so credentials/session cookies can't be sniffed in cleartext on the wire,
even on a LAN — but it's self-signed, so it doesn't give you a trust chain
a browser recognizes: expect a one-time browser warning, and it doesn't
protect against an active on-path attacker presenting *their own*
self-signed cert instead (true MITM protection needs a real CA-issued
cert — either paste one via the CDN's manual HTTPS mode and proxy the
panel through that, or put a real cert in front of 8080 yourself).

`/login` also has brute-force lockout built in (`panel/app/login_guard.py`):
after `LOGIN_MAX_ATTEMPTS` (default 5) failed attempts from one IP within
`LOGIN_FAIL_WINDOW_SECONDS` (default 15 min), that IP is locked out of
`/login` entirely — no password check even attempted — for
`LOGIN_LOCKOUT_BASE_SECONDS` (default 1 hour), **doubling on each further
violation** up to `LOGIN_LOCKOUT_MAX_SECONDS` (default 24h capped). A
successful login clears both the failure count and the escalation level.
Tracked in Redis, so it survives a panel restart. Tune via those env vars
(see `.env.example`) if the defaults are too strict/loose for you.

Beyond that: use a real random `ADMIN_PASSWORD`/`SESSION_SECRET`, and
consider firewalling port 8080 to a trusted network/VPN if you don't need
the panel reachable publicly at all.

## Offline builds

Both Dockerfiles are built to need **no PyPI/GitHub/luarocks.org network
access** at `docker build` time:

- `panel/vendor/wheels/` has every wheel needed to satisfy
  `panel/requirements.txt` (direct deps + full transitive closure, for both
  `x86_64` and `aarch64`) — the Dockerfile installs with `pip install
  --no-index --find-links=/wheels`. See `panel/vendor/wheels/VERSIONS.md`.
- `openresty/vendor/` has `lua-resty-auto-ssl` plus everything it normally
  fetches from GitHub/luarocks.org at build time (`lua-resty-http`,
  `shell-games`, `dehydrated`, `lua-resty-shell`'s `shell.lua`, and the
  `sockproc` C source) — the Dockerfile builds/installs all of it via
  `luarocks make` against the local source, and pre-seeds the exact files
  `lua-resty-auto-ssl`'s own `Makefile` would otherwise `curl` down. See
  `openresty/vendor/VERSIONS.md`.

What's **not** vendored, and why: each Dockerfile's own OS package install
(`apk add ...` for Alpine) still hits the base image's configured package
mirror — vendoring raw `.apk`/`.deb` binaries into git is fragile (tightly
version/arch-coupled to the exact base image). Pulling the base images
themselves (`python:3.12-slim`, `openresty/openresty:...-alpine-fat`,
`postgres:16-alpine`, `redis:7-alpine`, `pschiffe/pdns-pgsql:alpine`,
`traefik/whoami`) also still needs network the first time — that's
inherent to how Docker registries work. Run `docker compose up --build`
once with network access, and normal Docker layer caching keeps subsequent
rebuilds offline as long as those base image layers and this `vendor/`
content don't change.

## Repo layout

```
panel/       FastAPI admin panel (Python)
  vendor/wheels/   vendored pip wheels (offline build — see above)
openresty/   Edge: nginx.conf, conf.d/, Lua modules (router, WAF, auto-ssl)
  vendor/          vendored lua-resty-auto-ssl + its deps (offline build)
postgres/    DB init script (creates the `panel` and `pdns` databases)
deploy/      Optional systemd unit for boot-start
docker-compose.yml
.env.example
```

## Roadmap / known limitations

Contributions welcome on any of these:

- **Single admin user** — no RBAC/multi-tenant support yet.
- **IPv4-only** CIDR blocking (IPv6 CIDR matching isn't implemented).
- Deleting a domain in the panel does **not** delete its PowerDNS zone —
  manage zone deletion from the DNS page if you want that too.
- WAF events are kept in a capped Redis list (last 500), not a full log
  pipeline — fine for a single-server setup, not built for high-volume
  forensics.
- HTTPS relies on [`lua-resty-auto-ssl`](https://github.com/auto-ssl/lua-resty-auto-ssl)
  for on-the-fly Let's Encrypt certs. That project is archived/unmaintained
  upstream — it still works (uses `dehydrated` under the hood), but a
  `certbot`-based alternative would be a reasonable future swap.
- No Kubernetes manifests — Docker Compose only, by design.

## Troubleshooting

If a `docker compose up --build` doesn't come up clean, the likely spots to
check first:

- The vendored `luarocks make` build chain in `openresty/Dockerfile`
  (`openresty/vendor/`) — in particular the `sockproc` C compile and the
  "stamp file" trick that makes `lua-resty-auto-ssl`'s `Makefile` skip its
  normal network fetches.
- Exact PowerDNS env var behavior in `pschiffe/pdns-pgsql` (zone
  auto-creation, `webserver-allow-from`).
- `ssl_certificate_by_lua_block` / ACME flow, which needs port 80 reachable
  from the public internet to actually issue certificates.
- The vendored wheel set in `panel/vendor/wheels/` — if `pip install
  --no-index` complains about a missing/incompatible wheel, it's almost
  certainly a transitive dependency that's missing; check
  `panel/vendor/wheels/VERSIONS.md`.

Open an issue with the relevant `docker compose logs <service>` output and
what you were doing when it broke.

## Contributing

Issues and PRs welcome — bug reports, features from the roadmap above,
docs fixes, all good. No CI pipeline yet, so just make sure `docker compose
up --build` still comes up clean and the feature you touched still works
before opening a PR.

## License

[MIT](LICENSE) for Open-Shield's own code. Vendored third-party source
under `openresty/vendor/` and `panel/vendor/` keeps its own original
license (MIT/BSD-2-Clause — see the `LICENSE`/`LICENSE.txt` file inside
each vendored project's directory).
