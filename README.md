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

This also starts a `demo-origin` (traefik/whoami) container you can point a
domain's origin at for testing.

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
openresty/   Edge: nginx.conf, conf.d/, Lua modules (router, WAF, auto-ssl)
postgres/    DB init script (creates the `panel` and `pdns` databases)
docker-compose.yml
.env.example
```

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

- The `luarocks install lua-resty-auto-ssl` step in `openresty/Dockerfile`
  (native build step).
- Exact PowerDNS env var behavior in `pschiffe/pdns-pgsql` (zone
  auto-creation, `webserver-allow-from`).
- `ssl_certificate_by_lua_block` / ACME flow, which needs port 80 reachable
  from the public internet to actually issue certificates.
