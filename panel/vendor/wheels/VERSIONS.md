# Vendored wheels

Every wheel needed to satisfy `../../requirements.txt` offline — direct
dependencies and their full transitive closure, resolved against PyPI's
JSON API for exactly these pinned versions. Compiled (C-extension)
packages are vendored for both `manylinux ... x86_64` and `... aarch64`,
cp312; everything else is a universal (`py3-none-any`) wheel. All files
were verified against PyPI's published sha256 digest at fetch time.

`panel/Dockerfile` installs via `pip install --no-index --find-links=/wheels
-r requirements.txt` — pip still resolves the dependency graph normally, it
just never looks past this directory, so no PyPI network access happens at
build time.

| Package | Version | Why |
|---|---|---|
| fastapi | 0.115.6 | direct |
| starlette | 0.41.3 | fastapi |
| pydantic | 2.13.4 | fastapi |
| pydantic_core | 2.46.4 | pydantic (compiled) |
| typing_extensions | 4.16.0 | fastapi/pydantic/sqlalchemy/psycopg/anyio |
| typing_inspection | 0.4.4 | pydantic |
| annotated_types | 0.8.0 | pydantic |
| anyio | 4.14.2 | starlette/httpx |
| uvicorn | 0.32.1 | direct (base install, no `[standard]` extra — see below) |
| click | 8.4.2 | uvicorn |
| h11 | 0.16.0 | uvicorn/httpcore |
| sqlalchemy | 2.0.36 | direct (compiled) |
| greenlet | 3.5.5 | sqlalchemy, required on x86_64/aarch64 (compiled) |
| psycopg | 3.2.3 | direct |
| psycopg_binary | 3.2.3 | direct (`psycopg[binary]` extra, compiled, bundles libpq) |
| redis | 5.2.1 | direct |
| httpx | 0.28.1 | direct |
| certifi | 2026.7.22 | httpx/httpcore |
| httpcore | 1.0.9 | httpx |
| idna | 3.19 | httpx/anyio |
| jinja2 | 3.1.4 | direct |
| markupsafe | 3.0.3 | jinja2 (compiled) |
| passlib | 1.7.4 | direct (base install, no extras — we install `bcrypt` directly) |
| bcrypt | 4.0.1 | direct (compiled) |
| itsdangerous | 2.2.0 | direct |
| python_multipart | 0.0.19 | direct |

## `uvicorn[standard]` vs base `uvicorn`

`requirements.txt` pins plain `uvicorn`, not `uvicorn[standard]`. The
`[standard]` extra pulls in `uvloop`, `httptools`, `websockets`,
`watchfiles`, `python-dotenv` and `pyyaml` — a much larger, more
architecture-sensitive vendoring surface (several are Rust/C extensions)
for a performance benefit that doesn't matter much for an admin panel (the
actual WAF/CDN hot path is OpenResty, not this Python app). Base `uvicorn`
(asyncio + h11) is what's vendored here.

## Refreshing / adding a package

Bump the version (or add a new package) to the `PACKAGES` list logic
described above, then re-resolve via PyPI's JSON API
(`https://pypi.org/pypi/<name>/<version>/json`) — check `info.requires_dist`
for any new transitive dependencies gated on `python_version`/`sys_platform`
markers that apply to Python 3.12 / Linux, and fetch their wheels the same
way (pure wheel for `py3-none-any`/`py2.py3-none-any`, both
`manylinux ... x86_64` and `... aarch64` cp312 wheels for anything
compiled), verifying each download's sha256 against the JSON metadata.
