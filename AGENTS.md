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
- `docs/bdd.md` — BDD scenarios in Gherkin, tagged `KAL-<AREA>-<NNN>` + `@automated`/`@manual`
- `docs/roadmap.md` — quarterly roadmap (open-core direction)
- `docs/plans/` — one plan per unit of work; see `docs/plans/README.md` for lifecycle
- `README.md` — Project overview and quick start

## Working Agreement (Definition of Done)

Every task, no exceptions:

1. **Scope comes from a plan.** If the task references a file in
   `docs/plans/`, implement ONLY what that plan (or the named section)
   covers. "Not in scope" sections are binding. If work outside scope
   seems necessary, STOP and explain instead of doing it.
2. **Verify before claiming done.** Run `./scripts/verify.sh` and
   include its full output in your final report. A task with failing
   verification is not done — report it as blocked with the error.
3. **No silent production changes.** Test-only tasks must not modify
   `src/` except explicitly justified minimal hooks; call out every
   production file you touch and why.
4. **No green-washing.** Never add `skip`/`xfail`, loosen an
   assertion, raise a timeout, or add an `ignore_imports` entry to
   make checks pass without explaining the root cause first.
5. **New behaviour = new scenario.** If you add user-facing behaviour,
   add/update the `KAL-` scenario in `docs/bdd.md` (tag `@automated`
   only when a test covers it) and reference it in test docstrings
   (`Covers: KAL-XXX-NNN`).
6. **Architecture contracts are law.** `lint-imports` failures mean
   your design is wrong, not that the contract needs another ignore.
   The `TODO(q3-views-refactor)` ignore list may only shrink.
7. **Record decisions.** Non-obvious findings and resolved open
   questions go into the plan's `## Implementation notes`.
8. **E2e is mandatory for view changes.** Any change under
   `src/kaleta/views/` requires `./scripts/verify.sh --e2e`, not the
   short gate.
9. **Keep diffs single-purpose.** Repo-wide formatting, lint fixes in
   unrelated files, or drive-by refactors go in a separate commit (or
   are reported for the user to commit separately) — never mixed into
   the task's diff.

## Available Subagents

Use the `Agent` tool to delegate to these specialists. Trigger them proactively when the task matches their description — don't wait for the user to ask.

| Agent | When to use |
|---|---|
| `test-runner` | After any code change — verify tests pass; write unit tests for new services, schemas, or input fields |
| `docs-writer` | After features, bug fixes, or architectural changes — keep `docs/architecture.md`, `docs/tech-stack.md`, `README.md` in sync |
| `migration-creator` | After adding or changing any SQLAlchemy model in `src/kaleta/models/` — creates the Alembic migration file |
| `seed-updater` | After adding a new model — adds realistic Polish-language seed data to `scripts/seed.py` |
| `i18n-verifier` | After adding or modifying a NiceGUI view — checks all user-facing strings use `t()` and all keys exist in `en.json` / `pl.json` |
| `view-scaffolder` | When adding a completely new page — creates the view file, registers it in `main.py`, adds nav entry, wires service layer, adds i18n keys |
| `scenario-runner` | When implementing or running BDD end-to-end tests from `docs/bdd.md` using pytest-playwright against a live app instance (`http://localhost:8080`) |
| `ux-designer` | When evaluating UI flows, reviewing view files, or auditing UX against BDD scenarios — provides high-level recommendations based on Nielsen heuristics and Kaleta brand guidelines |
| `security-auditor` | After adding API endpoints, services, or any code handling user input/file uploads — runs Bandit static analysis and reports findings with remediation advice |
| `deps-updater` | Periodically or before releases — checks all packages for available updates, assesses upgrade risk, and applies safe updates to `pyproject.toml` + `uv.lock` |
