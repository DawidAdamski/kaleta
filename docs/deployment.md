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
KALETA_DB_URL=postgresql+asyncpg://...
KALETA_DEMO=true          # enables the dismissible demo banner in the UI
```

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

## Health check

After deploy, verify:

```bash
curl -sS https://your-demo.example/api/v1/health
```

Expect `"database_ok": true` and `"migrations_pending": false`.

## Related

- CI Postgres matrix: `.github/workflows/ci.yml` (`postgres` job)
- Plan: [`docs/plans/q4-supabase-deployment.md`](plans/q4-supabase-deployment.md)
- Observability (optional): [`docs/plans/observability-anonymous-events.md`](plans/observability-anonymous-events.md)
