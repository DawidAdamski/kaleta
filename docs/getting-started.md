# Getting started

Detailed setup, configuration, and development reference for Kaleta.

## Self-hosted or hosted

Kaleta runs two ways, from the same image — only the environment differs:

| | Self-hosted (this page) | Hosted ([deployment.md](deployment.md)) |
|---|---|---|
| Runs on | Your machine, or Podman on a small server | Supabase (Auth + PostgreSQL) and one app container |
| Accounts | One instance, families in schemas of their own; the first sign-up is the instance administrator | Many accounts, each in a schema of its own |
| Sign-in | E-mail and password, checked locally (`public.local_identities`) | E-mail sign-up through Supabase Auth |
| Encryption | Always on (`KALETA_ENCRYPTION=passphrase`) | Always on; the operator cannot read your data |
| Setting | `KALETA_AUTH_BACKEND=local` (default) | `KALETA_AUTH_BACKEND=supabase` |

Every instance uses the same layout on PostgreSQL 16+ (ADR-38): a `public`
registry plus one schema per family.

To try the hosted layout on a laptop without Supabase, run
`podman compose -f compose.hosted-dev.yml up -d --build` — PostgreSQL plus
local logins in debug mode — and open http://localhost:8090
([deployment.md](deployment.md#4-the-hosted-flow-on-a-laptop)).

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager
- PostgreSQL 16 or newer — or skip all three and use
  [Docker / Podman](#docker-podman)

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Install and run

```bash
uv sync
KALETA_DB_URL=postgresql://kaleta:<password>@localhost:5432/kaleta uv run kaleta
```

The role needs to own its database (it creates one schema per family). Open
**http://localhost:8080**. On every start Kaleta brings the registry and then
every family's schema to the installed Alembic head, and refuses to start if a
migration fails. The first sign-up on an empty instance
creates the instance administrator and the first family, using an e-mail
address and a password; it then asks for a data passphrase before any
financial data pages load.

### Forgotten password

If you forget the login password, the instance operator resets it from a shell:

```bash
uv run kaleta-admin reset-password <e-mail>
```

It prints a one-time password, which the member must replace at their next
sign-in. There is no email reset and no in-app “forgot password” flow. Every browser
session of that member is signed out (within a minute of the reset); API bearer
tokens are unchanged. `kaleta --reset-password` no longer exists. See
[SECURITY.md](../SECURITY.md). In the Compose stack, run it in the container:
`podman compose exec kaleta uv run kaleta-admin reset-password <e-mail>`.

### Demo data

Populate realistic Polish demo data — accounts, categories, payees, tags, six
years of transactions, budgets, planned transactions, subscriptions, reserve
funds, personal loans and a credit card:

```bash
uv run python scripts/seed.py              # add what is missing
uv run python scripts/seed.py --only transactions budgets
uv run python scripts/seed.py --replace    # rewrite the example data
uv run python scripts/seed.py --fresh      # drop and recreate the tables first
```

Every run is idempotent: a feature that already has example data is reported as
left alone rather than seeded twice. The same seeders sit behind
**Settings → Data → Example data**, one button per feature, so the CLI and the
UI produce the same dataset.

### Optional forecasting

Prophet is an **optional extra**, not a core dependency. Without it the app
starts normally and the Forecast page uses a lightweight seasonal-naive
projection with a banner explaining the fallback.

```bash
uv sync --extra forecast   # install Prophet + cmdstan (~300 MB)
```

Docker ships two images: `kaleta:slim` (default `Containerfile`, no Prophet)
and `kaleta:full` (`Containerfile.full`, includes the forecast extra).
Docker Compose uses the full image by default.

## Running modes

Set via the `KALETA_MODE` environment variable:

| Mode | Command | Description |
|------|---------|-------------|
| `web` (default) | `uv run kaleta` | Browser-accessible web app; install it as an app (PWA) from the browser |
| `api` | `KALETA_MODE=api uv run kaleta` | Headless REST API only |

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KALETA_DB_URL` | `postgresql+asyncpg://kaleta@localhost:5432/kaleta` | PostgreSQL 16+ URL; `postgresql://` is rewritten to the asyncpg driver, anything else is refused |
| `KALETA_HOST` | `127.0.0.1` | Host to bind to (`0.0.0.0` in Docker Compose) |
| `KALETA_PORT` | `8080` | Port to listen on |
| `KALETA_MODE` | `web` | Runtime mode (`web` / `api`) |
| `KALETA_SECRET_KEY` | `change-me-in-production` | Secret key for sessions (required outside debug) |
| `KALETA_DEBUG` | `false` | Enable debug mode (allows default secret key) |
| `KALETA_API_TOKEN` | _(unset)_ | Bootstrap bearer for `KALETA_MODE=api` (≥16 chars). On API startup with this set, Kaleta ensures a real user exists (creates locked user `api` if needed) so the token can authenticate. With local logins it acts as the instance administrator in their family. Tokens made in Settings remain the normal path. |
| `KALETA_SESSION_TTL_HOURS` | `72` | UI session lifetime in hours (`0` disables expiry) |
| `KALETA_SESSION_IDLE_HOURS` | `12` | Sign a UI session out after this many hours without a request (`0` disables; capped at `KALETA_SESSION_TTL_HOURS`) |
| `KALETA_SESSION_COOKIE_SECURE` | `false` | Mark the `kaleta_session` cookie `Secure` — only behind TLS; on plain http login stops working |
| `KALETA_SESSION_COOKIE_SAMESITE` | `lax` | `lax` or `strict` (`strict` drops the cookie on links from outside, e.g. e-mail confirmations) |
| `KALETA_NBP_FETCH` | `false` | Fetch NBP Table A exchange rates at start-up and once a day, for every family of the instance |
| `KALETA_ENCRYPTION` | `passphrase` | Field-level encryption; `off` is accepted only with `KALETA_DEBUG=true` — see [deployment.md](deployment.md) |
| `KALETA_AUTH_BACKEND` | `local` | `local` (logins in `public.local_identities`) or `supabase` |
| `KALETA_INSTANCE_ADMINS` | _(unset)_ | Instance administrators of a `supabase` instance, by e-mail (comma-separated). Local logins carry the flag themselves (the first sign-up, or `kaleta-admin create-login --admin`) |
| `KALETA_REDIS_URL` | _(unset)_ | Keep sessions and the login rate limiter in Valkey (or any Redis-protocol server), so several replicas share them (extra: `hosted`) — see [deployment.md](deployment.md#sessions-restarts-and-replicas) |

Any setting can also be a file under `/run/secrets` named after the variable
in lower case (`/run/secrets/kaleta_secret_key`); an environment variable of
the same name wins. The Compose stack hands Kaleta its secrets this way.

NiceGUI's session files live in `~/.kaleta/nicegui`. Kaleta runs with umask
`077`, so everything it writes there is readable by its own Unix user only.
Repo-root `.nicegui/` leftovers from older runs are safe to delete manually —
the app does not remove them.

Create a `.env` file in the project root to override defaults:

```env
KALETA_DB_URL=postgresql://kaleta:<password>@localhost:5432/kaleta
KALETA_HOST=127.0.0.1
KALETA_PORT=8080
KALETA_SECRET_KEY=your-secret-key-here
```

## Docker / Podman

Kaleta ships `Containerfile` (slim) and `Containerfile.full` (includes Prophet).
[`docker-compose.yml`](../docker-compose.yml) runs the **full** image with
PostgreSQL 18; the same file works with Docker Compose and Podman Compose.

From the repository root:

```bash
podman compose up -d --build     # or: docker compose up -d --build
```

Open **http://localhost:8080**. On an empty database the first sign-up creates
the instance administrator and the first family, then asks for the data
passphrase.

What the stack holds:

| Service / volume | What it is |
|------------------|------------|
| `secrets` | Runs once per `up`: writes the database password and `KALETA_SECRET_KEY` into `kaleta-secrets` if they are not there yet |
| `db` | `postgres:18-alpine`, data in the `kaleta-pg` volume |
| `kaleta` | The app on port 8080; reads `/run/secrets/kaleta_db_url` and `/run/secrets/kaleta_secret_key` |
| `kaleta-state` | NiceGUI's session files: a restarted container keeps its sessions and asks for the passphrase again |

Nothing secret is written in `docker-compose.yml`. Removing `kaleta-secrets`
while `kaleta-pg` stays would leave a database whose password nobody has —
keep the volumes together.

The administrator's CLI runs inside the container:

```bash
podman compose exec kaleta uv run kaleta-admin reset-password <e-mail>
podman compose exec kaleta uv run kaleta-admin registration open
```

Backups are the operator's (Kaleta makes none): `pg_dump` the database, e.g.

```bash
podman compose exec db pg_dump -U kaleta -Fc kaleta > kaleta-$(date +%F).dump
```

Every family can also export its own data from Settings → Data.

Behind a reverse proxy with HTTPS, add `KALETA_PUBLIC_URL` and
`KALETA_SESSION_COOKIE_SECURE=true` under `kaleta.environment`. To use the
slim image (no Prophet), point `kaleta.build.dockerfile` at `Containerfile`.

Bind to loopback on the host if you only use it locally — `127.0.0.1:8080:8080`
in `kaleta.ports`. For autostart without containers, see
[Local deploy](deploy-local.md).

## Development

See [Contributing on GitHub](https://github.com/DawidAdamski/kaleta/blob/main/CONTRIBUTING.md)
for the Working Agreement and PR process.

```bash
uv sync --group dev
./scripts/verify.sh          # add --e2e when changing views/; starts the test database
./scripts/test_db.sh up      # the tests run on PostgreSQL only — a throwaway server on :55432
uv run pytest
uv run ruff check .
uv run mypy src/
```

After model changes:

```bash
uv run alembic revision --autogenerate -m "description"
# Starting the app migrates the registry and every family's schema.
```

## Project structure

```
src/kaleta/
├── main.py          # Entrypoint
├── config/          # Settings via pydantic-settings
├── db/              # Engine, session factory, base model
├── models/          # SQLAlchemy ORM models
├── schemas/         # Pydantic request/response schemas
├── services/        # Business logic
├── seeders/         # Per-feature example data (one module per feature)
├── core/            # Pure helpers shared by every layer (week bucketing, …)
├── api/             # REST API (versioned under api/v1/)
└── views/           # NiceGUI UI pages
scripts/
└── seed.py          # Thin CLI over src/kaleta/seeders/
tests/
├── unit/
├── integration/
└── e2e/             # Playwright browser tests
```

## Features

Kaleta is a self-hosted personal finance app. Capabilities include:

- Transaction tracking with categories, accounts, splits, and filters
- Budget creation, monitoring, and annual planning grid
- CSV import with Polish bank format auto-detection and transfer detection
- Multi-currency accounts, net worth, and physical assets
- Cash flow forecasting (Prophet optional, seasonal-naive fallback)
- Planned and recurring transactions
- Credit cards, loans, and amortisation calculator
- Subscriptions detection, payment calendar, and financial wizard panels
- Customisable dashboard with drag-and-drop widgets
- Progressive Web App (PWA) support and REST API
- PostgreSQL 16+, one schema per family

For product design detail see [Product overview](product/index.md).

## License

Kaleta core is [AGPL-3.0-or-later](https://github.com/DawidAdamski/kaleta/blob/main/LICENSE).
External contributors sign the [Contributor License Agreement](cla.md). See
[ADR-033](adr/033-agpl-core-with-cla.md).
