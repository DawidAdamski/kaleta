# Kaleta - AI Assistant Context

## What is Kaleta?
Kaleta (Polish: leather money pouch) is a personal budget & finance management app.
It handles budgeting, transactions, financial planning, savings, and investments.

## Tech Stack
- **Language**: Python 3.13+
- **Package Manager**: uv (NOT pip)
- **UI**: NiceGUI 2.x (wraps FastAPI/Starlette)
- **API**: FastAPI (exposed via NiceGUI, also standalone)
- **ORM**: SQLAlchemy 2.0 (async-ready)
- **Validation**: Pydantic v2 (schemas separate from models)
- **Database**: SQLite (default) / PostgreSQL (optional)
- **Migrations**: Alembic
- **Forecasting**: Prophet (time-series forecasting for budget trends)
- **Deployment**: Docker / Podman

## Architecture: MVC + Service Layer

```
Views (NiceGUI) + API (FastAPI)
        ↓
   Controllers (orchestration)
        ↓
   Services (business logic)
        ↓
   Models (SQLAlchemy) + Schemas (Pydantic)
        ↓
   Database (SQLite / PostgreSQL)
```

## Project Layout
```
src/kaleta/
├── main.py              # Entrypoint
├── config/              # Settings via pydantic-settings (env vars)
├── db/                  # Engine, session factory, base model
├── models/              # SQLAlchemy ORM models
├── schemas/             # Pydantic request/response schemas
├── services/            # Business logic (no HTTP concerns)
├── controllers/         # Route handlers, ties services to views/API
├── api/                 # REST API routes (versioned under api/v1/)
└── views/               # NiceGUI UI pages
tests/
├── unit/
└── integration/
docs/                    # Architecture ADRs, tech stack, product docs
```

## Coding Conventions

### Style
- **Object-oriented, class-based** code — no loose functions for features
- Ruff for linting + formatting (line length 100)
- mypy strict mode for type checking
- pytest for testing

### Patterns
- Services contain business logic; controllers are thin
- Pydantic schemas are separate from SQLAlchemy models (never use ORM models in API responses)
- Use dependency injection for database sessions
- All database operations go through services, never directly in views/controllers
- Keep SQLite compatibility — avoid PostgreSQL-only features in models

### Naming
- Files: `snake_case.py`
- Classes: `PascalCase`
- Models: singular noun (`Transaction`, `Budget`, `Account`)
- Schemas: suffixed with purpose (`TransactionCreate`, `TransactionResponse`)
- Services: suffixed with `Service` (`TransactionService`)
- Controllers: suffixed with `Controller` (`TransactionController`)

## Commands
```bash
uv sync                      # Install dependencies
uv sync --extra dev          # Install with dev tools
uv sync --extra postgres     # Install with PostgreSQL driver
uv run kaleta                # Run the app (web mode)
uv run pytest                # Run tests
uv run ruff check .          # Lint
uv run ruff format .         # Format
uv run mypy src/             # Type check
```

## Runtime Modes
Set via `KALETA_MODE` environment variable:
- `web` (default) — browser-accessible web app
- `app` — NiceGUI desktop window
- `api` — headless REST API only

## Environment Variables
```
KALETA_DB_URL=sqlite:///kaleta.db
KALETA_HOST=0.0.0.0
KALETA_PORT=8080
KALETA_MODE=web
KALETA_SECRET_KEY=<change-me>
KALETA_DEBUG=false
```

## Key Documents
- `docs/architecture.md` — Architecture Decision Records
- `docs/tech-stack.md` — Technology choices and config reference
- `README.md` — Project overview and quick start
