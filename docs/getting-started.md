# Getting started

Detailed setup, configuration, and development reference for Kaleta.

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Install and run

```bash
uv sync
uv run kaleta
```

Open **http://localhost:8080**. On first launch you choose a database location
(migrations run in the wizard); on later starts the app brings the configured
database up to the installed alembic head automatically. Then create a username
and password before any financial data pages load.

### Forgotten password

If you forget the login password, reset it interactively against the same
database the app uses (`~/.kaleta/config.json`):

```bash
uv run kaleta --reset-password
```

You will be prompted for a new password and confirmation (minimum 8 characters).
There is no email reset and no in-app “forgot password” flow. Existing browser
sessions may still work until you sign out or clear site data; API bearer tokens
are unchanged. See [SECURITY.md](../SECURITY.md).

To migrate the **configured** database by hand (for example after restoring a
file copy), point Alembic at that URL — bare `uv run alembic upgrade head`
uses `KALETA_DB_URL` (default: `kaleta.db` in the current working directory),
which is often **not** the live DB from `~/.kaleta/config.json`:

```bash
KALETA_MIGRATE_URL=sqlite+aiosqlite:///$HOME/KaletaData/kaleta.db uv run alembic upgrade head
```

### Demo data

Populate realistic Polish demo data (accounts, categories, transactions,
budgets):

```bash
uv run python scripts/seed.py
```

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
| `web` (default) | `uv run kaleta` | Browser-accessible web app |
| `app` | `KALETA_MODE=app uv run kaleta` | NiceGUI desktop window |
| `api` | `KALETA_MODE=api uv run kaleta` | Headless REST API only |

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KALETA_DB_URL` | `sqlite+aiosqlite:///{home}/.kaleta/kaleta.db` | Database connection URL (default under `~/.kaleta`) |
| `KALETA_HOST` | `127.0.0.1` | Host to bind to (`0.0.0.0` in Docker Compose) |
| `KALETA_PORT` | `8080` | Port to listen on |
| `KALETA_MODE` | `web` | Runtime mode (`web` / `app` / `api`) |
| `KALETA_SECRET_KEY` | `change-me-in-production` | Secret key for sessions (required outside debug) |
| `KALETA_DEBUG` | `false` | Enable debug mode (allows default secret key) |
| `KALETA_API_TOKEN` | _(unset)_ | Bootstrap bearer for `KALETA_MODE=api` (≥16 chars). On API startup with this set, Kaleta ensures a real user exists (creates locked user `api` if needed) so the token can authenticate. UI-managed tokens remain the normal path for `web`/`app`. |
| `KALETA_SESSION_TTL_HOURS` | `72` | UI session lifetime in hours (`0` disables expiry) |
| `KALETA_BACKUP_ENABLED` | `true` | Enable scheduled SQLite `VACUUM INTO` backups |
| `KALETA_BACKUP_INTERVAL_HOURS` | `24` | Hours between scheduled backups |
| `KALETA_BACKUP_RETAIN` | `7` | Keep the last K `kaleta-*.db` files |
| `KALETA_BACKUP_DIR` | `~/.kaleta/backups` | Directory for on-disk SQLite snapshots (not ZIP exports) |

Keep production data under `~/.kaleta` (database, NiceGUI sessions in
`~/.kaleta/nicegui`, backups). Repo-root `*.db` / `.nicegui/` leftovers from
older runs are safe to delete manually — the app does not remove them.

Create a `.env` file in the project root to override defaults:

```env
KALETA_DB_URL=sqlite+aiosqlite:////Users/you/.kaleta/kaleta.db
KALETA_HOST=127.0.0.1
KALETA_PORT=8080
KALETA_SECRET_KEY=your-secret-key-here
```

## Docker / Podman

Kaleta ships `Containerfile` (slim) and `Containerfile.full` (includes Prophet).
[`docker-compose.yml`](../docker-compose.yml) builds the **full** image by default
and persists SQLite under a named volume. The same Compose file works with
Docker Compose or Podman Compose.

Open **http://localhost:8080** after the container is up. First visit still runs
setup (database + account) unless you already have data on the volume.

### Compose (named volume)

From the repository root:

```bash
# Docker
docker compose up --build

# Podman (either form, depending on your install)
podman compose up --build
# or:
podman-compose up --build
```

Compose sets:

| Variable / mount | Value |
|------------------|--------|
| `KALETA_DB_URL` | `sqlite:///data/kaleta.db` → file `/app/data/kaleta.db` |
| `KALETA_HOST` | `0.0.0.0` |
| Volume `kaleta-data` | mounted at `/app/data` |

Set a real secret (required when `KALETA_DEBUG` is not true):

```bash
export KALETA_SECRET_KEY="$(openssl rand -hex 32)"
podman compose up --build
```

Or add under `environment:` in `docker-compose.yml`:

```yaml
- KALETA_SECRET_KEY=replace-with-a-long-random-string
```

Stop with `Ctrl+C`, or detach with `-d`. Data survives container recreation
as long as the `kaleta-data` volume remains.

Inspect / remove the volume (destructive):

```bash
podman volume ls
podman volume inspect kaleta_kaleta-data   # name may include the project prefix
# podman volume rm kaleta_kaleta-data
```

### Bind-mount a host folder

Keep the database on the host (easy backups, visible files):

```bash
mkdir -p "$HOME/KaletaData/backups"

podman build -f Containerfile.full -t kaleta:full .

podman run --name kaleta --rm -it \
  -p 8080:8080 \
  -e KALETA_HOST=0.0.0.0 \
  -e KALETA_PORT=8080 \
  -e KALETA_DB_URL=sqlite:///data/kaleta.db \
  -e KALETA_BACKUP_DIR=/data/backups \
  -e KALETA_SECRET_KEY="$(openssl rand -hex 32)" \
  -v "$HOME/KaletaData:/app/data:Z" \
  kaleta:full
```

- Host path `$HOME/KaletaData` maps to `/app/data` in the container.
- `:Z` is for SELinux (Fedora/RHEL); on macOS you can omit it:
  `-v "$HOME/KaletaData:/app/data"`.
- SQLite file: `$HOME/KaletaData/kaleta.db`.
- Scheduled backups (if enabled): `$HOME/KaletaData/backups/`.

Equivalent with Docker:

```bash
docker build -f Containerfile.full -t kaleta:full .
docker run --name kaleta --rm -it \
  -p 8080:8080 \
  -e KALETA_HOST=0.0.0.0 \
  -e KALETA_PORT=8080 \
  -e KALETA_DB_URL=sqlite:///data/kaleta.db \
  -e KALETA_BACKUP_DIR=/data/backups \
  -e KALETA_SECRET_KEY="$(openssl rand -hex 32)" \
  -v "$HOME/KaletaData:/app/data" \
  kaleta:full
```

### Slim image (no Prophet)

Smaller image if you do not need forecasting:

```bash
podman build -f Containerfile -t kaleta:slim .
# same podman run as above, image kaleta:slim
```

### Notes

- Prefer **one** persistent store (Compose volume **or** bind mount). Mixing a
  host `uv run kaleta` install (`~/.kaleta`) with a container volume means two
  separate databases unless you deliberately point both at the same file.
- Bind to loopback on the host if you only use it locally, e.g.
  `-p 127.0.0.1:8080:8080`, instead of publishing on all interfaces.
- For non-container autostart on the host, see [Local deploy](deploy-local.md).

## Development

See [Contributing on GitHub](https://github.com/DawidAdamski/kaleta/blob/main/CONTRIBUTING.md)
for the Working Agreement and PR process.

```bash
uv sync --group dev
./scripts/verify.sh          # add --e2e when changing views/
uv run pytest
uv run ruff check .
uv run mypy src/
```

After model changes:

```bash
uv run alembic revision --autogenerate -m "description"
# Prefer starting the app (auto-migrate) or set KALETA_MIGRATE_URL to the target DB:
KALETA_MIGRATE_URL=sqlite+aiosqlite:///./kaleta.db uv run alembic upgrade head
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
├── api/             # REST API (versioned under api/v1/)
└── views/           # NiceGUI UI pages
scripts/
└── seed.py          # Demo data generator
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
- SQLite (default) or PostgreSQL

For product design detail see [Product overview](product/index.md).

## License

Kaleta core is [AGPL-3.0-or-later](https://github.com/DawidAdamski/kaleta/blob/main/LICENSE).
External contributors sign the [Contributor License Agreement](cla.md). See
[ADR-033](adr/033-agpl-core-with-cla.md).
