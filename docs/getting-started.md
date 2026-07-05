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
uv run alembic upgrade head
uv run kaleta
```

Open **http://localhost:8080**. On first launch you choose a database location,
then create a username and password before any financial data pages load.

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
| `KALETA_DB_URL` | `sqlite:///kaleta.db` | Database connection URL |
| `KALETA_HOST` | `127.0.0.1` | Host to bind to (`0.0.0.0` in Docker Compose) |
| `KALETA_PORT` | `8080` | Port to listen on |
| `KALETA_MODE` | `web` | Runtime mode (`web` / `app` / `api`) |
| `KALETA_SECRET_KEY` | `change-me-in-production` | Secret key for sessions (required outside debug) |
| `KALETA_DEBUG` | `false` | Enable debug mode (allows default secret key) |
| `KALETA_API_TOKEN` | _(unset)_ | Optional bootstrap bearer token for `KALETA_MODE=api` |

Create a `.env` file in the project root to override defaults:

```env
KALETA_DB_URL=sqlite:///kaleta.db
KALETA_HOST=127.0.0.1
KALETA_PORT=8080
KALETA_SECRET_KEY=your-secret-key-here
```

## Docker

```bash
# Full image (Prophet forecasting) — default in docker-compose
docker compose up

# Slim image (no Prophet, ~300 MB smaller)
docker build -f Containerfile -t kaleta:slim .
docker run -p 8080:8080 kaleta:slim

# Or using Podman
podman-compose up
```

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
uv run alembic upgrade head
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
