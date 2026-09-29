# Hosted deployment (Supabase Postgres)

Guide for running Kaleta against **Supabase Postgres** as the database
backend and operating a **public demo** instance. Application hosting is
separate — Supabase provides only the database.

For localhost autostart (launchd / systemd), see
[deploy-local.md](deploy-local.md). For Docker/Podman basics, see
[getting-started.md](getting-started.md).

## Overview

| Component | Role |
|---|---|
| Supabase Postgres | Persistent database (production path under test) |
| Kaleta app host | Runs the `kaleta:full` container or `uv run kaleta` |
| `scripts/reset_demo.py` | Nightly job that re-seeds demo data |

Secrets (`KALETA_DB_URL`, `KALETA_SECRET_KEY`) are **env-only** — never
commit them to the repo.

## Recommended rollout (2026-08)

1. **Start with Supabase** for Postgres + the public demo (this doc).
2. **App host:** any container platform that runs `kaleta:full` with the
   env block below (Fly.io, Railway, a small VPS — owner choice).
3. **Hetzner (or similar) later** — optional migration if Supabase + app
   host prove stable and cost/ops warrant a move.
4. **Commercial / shop layer** (e.g. [EasyTools](https://www.easy.tools/pl/cennik))
   is out of scope until pricing and paid features are defined.

## Supabase connection strings

Kaleta uses **async SQLAlchemy** with **asyncpg**. Set
`KALETA_DB_URL` using the `postgresql+asyncpg://` scheme (the app
rewrites bare `postgresql://` automatically, but being explicit avoids
surprises).

### Session pooler (app runtime)

Use the **session pooler** (port **6543**, IPv4-friendly) for the running
web process:

```env
KALETA_DB_URL=postgresql+asyncpg://postgres.[project-ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres?ssl=require
```

### Direct connection (migrations)

Run Alembic against the **direct** connection (port **5432**):

```env
KALETA_MIGRATE_URL=postgresql+asyncpg://postgres.[project-ref]:[password]@db.[project-ref].supabase.co:5432/postgres?ssl=require
uv run alembic upgrade head
```

`KALETA_MIGRATE_URL` is read by Alembic only; the app continues to use
`KALETA_DB_URL` via the pooler.

## Required environment variables

```env
KALETA_MODE=web
KALETA_HOST=0.0.0.0
KALETA_PORT=8080
KALETA_SECRET_KEY=<long-random-string>
KALETA_SESSION_COOKIE_SECURE=true   # hosted behind TLS only — see below
KALETA_SESSION_COOKIE_SAMESITE=lax  # or strict; strict breaks e-mail links
KALETA_DB_URL=postgresql+asyncpg://...
KALETA_DEMO=true          # enables the dismissible demo banner in the UI
```

`KALETA_SESSION_COOKIE_SECURE=true` marks the session cookie `Secure`: the
browser never sends it over plain http, so **login silently stops working**
on an install that is not served over TLS. Leave it `false` for local or
plain-http use. `KALETA_SESSION_COOKIE_SAMESITE` accepts `lax` (default) or
`strict`; `strict` drops the cookie on any navigation that starts outside the
app, including "confirm your e-mail" links. The cookie is named
`kaleta_session` and expires after `KALETA_SESSION_TTL_HOURS` (Starlette's
14-day default when the TTL is `0`).

> **Release note:** the session cookie was renamed from `session` to
> `kaleta_session`, which signs every browser out once after upgrading.

Optional but recommended for a hosted demo:

```env
KALETA_DEBUG=false
KALETA_BACKUP_ENABLED=false   # SQLite backups are irrelevant on Postgres
```

## First-time bootstrap

1. Create a Supabase project and copy connection strings (pooler + direct).
2. Run migrations on an empty database:

   ```bash
   export KALETA_MIGRATE_URL='postgresql+asyncpg://...:5432/postgres?ssl=require'
   uv sync --extra postgres
   uv run alembic upgrade head
   ```

3. Seed the demo user and dataset:

   ```bash
   export KALETA_DB_URL='postgresql+asyncpg://...:6543/postgres?ssl=require'
   export KALETA_DEMO=true
   export KALETA_SECRET_KEY='...'
   uv run python scripts/reset_demo.py
   ```

   This writes `~/.kaleta/config.json` with the active `db_url`, creates
   (or resets) the single demo user, and loads six years of Polish-language
   sample data.

4. Start the app with the same `KALETA_DB_URL` and `KALETA_DEMO=true`.

### Demo credentials

Published login for the public demo (fixed — the nightly reset does **not**
rotate the password):

| Field | Value |
|---|---|
| Username | `demo` |
| Password | `demo-kaleta` |

Document the live URL in `README.md` once hosting is in place (`[manual]`
acceptance criterion in the deployment plan).

## Daily demo reset

Schedule `scripts/reset_demo.py` to run once per day (host cron, systemd
timer, or GitHub Actions against a self-hosted runner with network access
to Supabase).

Example cron (03:00 UTC):

```cron
0 3 * * * cd /opt/kaleta && KALETA_DEMO=true KALETA_DB_URL='postgresql+asyncpg://...' KALETA_SECRET_KEY='...' /usr/local/bin/uv run python scripts/reset_demo.py >> /var/log/kaleta-demo-reset.log 2>&1
```

The script refuses to run unless `KALETA_DEMO=true` (use `--force` only
for local testing).

## App hosting (open question)

Supabase does **not** run the Python process. Pick a container host and
deploy the `kaleta:full` image with the env block above plus HTTPS in
front. Candidates from the plan:

- **Fly.io** — straightforward container deploy, modest free tier
- **Railway** — similar managed container flow
- **Hetzner VPS** — lowest long-term cost, more ops

Whichever host you choose, terminate TLS at the edge and keep
`KALETA_HOST=0.0.0.0` inside the container (see `docker-compose.yml`).

## Session state and replicas

A browser's session — who is signed in, when, plus preferences such as dark
mode — lives in NiceGUI's `app.storage.user`. The failed-login counters live
in the rate limiter. Where both are kept is one variable:

```env
KALETA_REDIS_URL=redis://:password@valkey-host:6379/0   # needs: uv sync --extra hosted
```

The server can be anything that speaks the Redis protocol. **Valkey is the
recommended one** (BSD-licensed, the Linux Foundation fork of Redis 7.2; CI
runs against `valkey/valkey:8`); Redis itself or a managed Redis-compatible
service (Upstash, ElastiCache/Memorystore for Valkey, Aiven) work the same.
The variable keeps "Redis" in its name because that is the protocol, the
`redis://` URL scheme and the client library (`redis-py`, which NiceGUI
uses too) — nothing in Kaleta is tied to the Redis server.

| `KALETA_REDIS_URL` | Sessions | Login rate limiter |
|---|---|---|
| unset (default) | one JSON file per browser in `~/.kaleta/nicegui` | a dict in the process |
| set | keys `kaleta:user-<id>` (via `NICEGUI_REDIS_URL`) | keys `kaleta:login:<ip>`, `kaleta:mfa:<user id>` |

**Single replica on a volume (cheaper, default).** One app process with
`~/.kaleta` on a persistent volume needs no Redis: sessions survive a restart
in the files, and a restart resets the failed-login counts (five fresh tries
per address). Pick this until you need a second replica.

**Two or more replicas.** Set `KALETA_REDIS_URL` on every replica, all
pointing at the same Valkey. Sessions and the lock after five failed logins
are then shared, and both survive a restart of any replica. NiceGUI keeps a
copy of each session in every process and syncs changes over Redis pub/sub
after the write, not before the next request — so **keep sticky sessions on
the load balancer**: a browser that bounces between replicas mid-login may
briefly see the state from before it. Session keys in Redis have no TTL; the
app's own `KALETA_SESSION_TTL_HOURS` / `KALETA_SESSION_IDLE_HOURS` still end
the session, and a `maxmemory-policy` of `allkeys-lru` bounds the rest.

**Permission model.** Nothing secret goes into session storage — no password
hash, TOTP secret, recovery code or key (ADR-035, enforced by
`tests/unit/auth/test_session_contents.py`). The files still say who is
signed in, so Kaleta runs with umask `077`: `~/.kaleta/nicegui` is `0700` and
each session file `0600`, readable only by the Unix user that runs Kaleta,
even when the data volume is shared with other services. Startup also
tightens files left behind by older versions. On Windows modes are not
touched. Everything else Kaleta writes (database, backups, exports) is
owner-only for the same reason — a deliberate widening: **a sidecar that
reads the volume under another uid** (a backup shipper, say) can no longer
read new files. Run such a sidecar under Kaleta's uid; the umask is not
configurable.

## Health check

After deploy, verify:

```bash
curl -sS https://your-demo.example/api/v1/health
```

Expect `"database_ok": true` and `"migrations_pending": false`.

## Related

- CI Postgres matrix: `.github/workflows/ci.yml` (`postgres` job)
- CI Valkey mode (sessions + rate limiter): `.github/workflows/ci.yml` (`redis` job, `valkey/valkey:8`)
- Plan: [`docs/plans/archive/q4-supabase-deployment.md`](plans/archive/q4-supabase-deployment.md)
- Observability: [`docs/privacy-events.md`](privacy-events.md)
