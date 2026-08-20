# Open-Shield

A self-hosted, Cloudflare-style platform: a Python admin panel for managing
**DNS**, a reverse-proxy **CDN** in front of your origins, and a **WAF**
that inspects headers/URL/body and can block by IP/CIDR or matching
strings/regex — all shipped as Docker images you run with `docker compose`.

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

## Quick start

```sh
cp .env.example .env
# edit .env: set real passwords/secrets, PDNS_DEFAULT_NS, EDGE_PUBLIC_HOST, ACME_EMAIL

docker compose up --build
```

Then open `http://localhost:8080` and log in with `ADMIN_EMAIL` /
`ADMIN_PASSWORD` from your `.env`.

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
stays on the isolated `openshield` bridge network as before — only `redis`
additionally publishes to `127.0.0.1:6379` so the now-host-networked
`openresty` can still reach it.

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

### HTTPS modes

Each domain has its own **HTTPS** setting on the domain form:

- **Off** (default) — served over plain HTTP only, port 80, no redirect to
  HTTPS. No DNS/ACME/certificate setup required — this is the easiest way to
  get a domain (or `demo-origin` for local testing) working end-to-end
  through the CDN/WAF immediately.
- **Automatic** — the existing Let's Encrypt flow via `lua-resty-auto-ssl`.
  Requires `EDGE_PUBLIC_HOST` set, the domain's DNS actually pointed at this
  server, and port 80 reachable from the public internet for the ACME
  HTTP-01 challenge.
- **Manual** — paste your own certificate (PEM, full chain) and private key
  (PEM) directly into the domain form. OpenResty picks it up on the next TLS
  handshake — no reload needed. Leave both boxes blank on an edit to keep
  the currently stored cert.

Domains with HTTPS on ("automatic" or "manual") get all plain-HTTP traffic
301-redirected to HTTPS; domains with HTTPS "off" are served on port 80 only
(hitting port 443 for one of these still works — the WAF/routing pipeline
runs the same way — but you'll get a browser certificate warning, since only
the edge's self-signed fallback cert is presented).

## Repo layout

```
panel/       FastAPI admin panel (Python)
  vendor/wheels/   vendored pip wheels (offline build — see below)
openresty/   Edge: nginx.conf, conf.d/, Lua modules (router, WAF, auto-ssl)
  vendor/          vendored lua-resty-auto-ssl + its deps (offline build)
postgres/    DB init script (creates the `panel` and `pdns` databases)
docker-compose.yml
.env.example
```

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
(`apk add ...` for Alpine, none needed anymore for the Debian-based panel
image) still hits the base image's configured package mirror — vendoring
raw `.apk`/`.deb` binaries into git is fragile (tightly version/arch-coupled
to the exact base image) and something that couldn't be verified working in
the sandbox this was built in. Pulling the base images themselves
(`python:3.12-slim`, `openresty/openresty:...-alpine-fat`, `postgres:16-alpine`,
`redis:7-alpine`, `pschiffe/pdns-pgsql:alpine`, `traefik/whoami`) also still
needs network the first time — that's inherent to how Docker registries
work and isn't something a git repo can vendor around; run `docker compose
up --build` once with network access, and normal Docker layer caching keeps
subsequent rebuilds offline as long as those base image layers and this
`vendor/` content don't change.

## Known limitations / v1 scope

- **Single admin user**, no RBAC/multi-tenant support yet.
- **IPv4-only** CIDR blocking (IPv6 CIDR matching isn't implemented).
- Deleting a domain in the panel does **not** delete its PowerDNS zone —
  manage zone deletion from the DNS page if you want that too.
- WAF events are kept in a capped Redis list (last 500), not a full log
  pipeline — fine for a single-server setup, not built for high-volume
  forensics.
- HTTPS relies on [`lua-resty-auto-ssl`](https://github.com/GUI/lua-resty-auto-ssl)
  for on-the-fly Let's Encrypt certs. That project is now archived/unmaintained
  upstream — it still works (uses `dehydrated` under the hood), but if you'd
  rather not depend on it, swapping in a `certbot` sidecar + static certs is
  a reasonable alternative for a future iteration.
- No Kubernetes manifests — Docker Compose only, by design.
- This was built and reviewed without a live Docker environment to test
  against (see below) — treat the first `docker compose up --build` as the
  real integration test, and expect to iterate on it.

## Testing this yourself

This was developed in a sandboxed environment without Docker available, so
it was verified statically (Python syntax checks; manual review of the Lua
modules against the `lua-resty-redis`/`lua-resty-auto-ssl` APIs and the
PowerDNS HTTP API docs) rather than by actually running the stack. Please
run `docker compose up --build` and go through the quick-start steps above —
if anything breaks, the likely trouble spots are:

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
  certainly a transitive dependency I missed; check
  `panel/vendor/wheels/VERSIONS.md`.
