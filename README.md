# Kaleta

**Kaleta** (Polish: *leather money pouch*) is a personal budget and finance management application.

Track transactions, create budgets, import bank CSV exports, and forecast your cash flow — all from a self-hosted web app or desktop window.

## Features

- Transaction tracking with categories and accounts
- Split transactions across multiple categories (GnuCash-style)
- Transaction filtering by account, category, type, date range, and description
- Budget creation and monitoring (budget vs. actual charts)
- CSV import with auto-detection of Polish bank formats
- Internal transfer detection between accounts
- Net worth tracking with 13-month history chart, asset/liability breakdown, and physical asset management (real estate, vehicles, valuables)
- Cash flow forecasting with Prophet (30–60 day horizon)
- REST API for integrations
- SQLite (default) or PostgreSQL

---

## Quick Start

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 1. Install dependencies

```bash
uv sync
```

### 2. Run database migrations

```bash
uv run alembic upgrade head
```

### 3. (Optional) Load seed data

Populates the database with realistic Polish demo data (4 accounts, 19 categories, ~240 transactions, 8 budgets):

```bash
uv run python scripts/seed.py
```

### 4. Start the application

```bash
uv run kaleta
```

Open your browser at **http://localhost:8080**

---

## Running Modes

Set via the `KALETA_MODE` environment variable:

| Mode | Command | Description |
|------|---------|-------------|
| `web` (default) | `uv run kaleta` | Browser-accessible web app |
| `app` | `KALETA_MODE=app uv run kaleta` | NiceGUI desktop window |
| `api` | `KALETA_MODE=api uv run kaleta` | Headless REST API only |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KALETA_DB_URL` | `sqlite:///kaleta.db` | Database connection URL |
| `KALETA_HOST` | `0.0.0.0` | Host to bind to |
| `KALETA_PORT` | `8080` | Port to listen on |
| `KALETA_MODE` | `web` | Runtime mode (`web` / `app` / `api`) |
| `KALETA_SECRET_KEY` | `change-me` | Secret key for sessions |
| `KALETA_DEBUG` | `false` | Enable debug mode |

Create a `.env` file in the project root to override defaults:

```env
KALETA_DB_URL=sqlite:///kaleta.db
KALETA_PORT=8080
KALETA_SECRET_KEY=your-secret-key-here
```

---

## Docker

```bash
# Using Docker Compose
docker compose up

# Or using Podman
podman-compose up
```

---

## Development

```bash
# Install with dev dependencies
uv sync --extra dev

# Run tests
uv run pytest

# Lint and format
uv run ruff check .
uv run ruff format .

# Type checking
uv run mypy src/

# Create a new migration after model changes
uv run alembic revision --autogenerate -m "description"
uv run alembic upgrade head
```

---

## Project Structure

```
src/kaleta/
├── main.py          # Entrypoint
├── config/          # Settings via pydantic-settings
├── db/              # Engine, session factory, base model
├── models/          # SQLAlchemy ORM models
├── schemas/         # Pydantic request/response schemas
├── services/        # Business logic
├── controllers/     # Route handlers
├── api/             # REST API (versioned under api/v1/)
└── views/           # NiceGUI UI pages
scripts/
└── seed.py          # Demo data generator (Faker, Polish locale)
tests/
├── unit/
│   ├── schemas/     # Pydantic validation tests
│   ├── services/    # Service layer tests
│   └── security/    # SQL injection, XSS, input security tests
└── integration/
```

---

## Documentation

- [Architecture](docs/architecture.md) — Architecture decisions and patterns
- [Tech Stack](docs/tech-stack.md) — Technology choices and configuration

## License

MIT
