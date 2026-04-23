# Kaleta - Technical Stack

## Core

| Component        | Technology           | Purpose                                        |
|------------------|----------------------|------------------------------------------------|
| Language         | Python 3.13+         | Primary language                               |
| Package Manager  | uv                   | Dependency management, venv, scripts           |
| UI Framework     | NiceGUI 2.x          | Web UI, app mode, desktop mode                 |
| Web Framework    | FastAPI (via NiceGUI) | REST API, request handling                    |
| ORM              | SQLAlchemy 2.x       | Database models, async queries                 |
| Migrations       | Alembic              | Schema migrations (`render_as_batch=True`)     |
| Validation       | Pydantic 2.x         | Data validation, serialization                 |
| Configuration    | pydantic-settings    | Environment-based config                       |
| ASGI Server      | Uvicorn              | Production server                              |

## Analytics & Forecasting

| Component        | Technology  | Purpose                                                       |
|------------------|-------------|---------------------------------------------------------------|
| Forecasting      | Prophet     | 30–60 day cash flow forecasting with seasonality & CI band    |
| Charts           | ECharts     | Budget vs actual, cash flow, forecast charts via `ui.echart` |

## Database

| Option           | Use Case                                      |
|------------------|-----------------------------------------------|
| SQLite (default) | Single-user, local, zero-config               |
| PostgreSQL (opt) | Multi-user, production, advanced features     |

Enum columns use `SAEnum(..., native_enum=False)` for SQLite round-trip compatibility.
Migrations use `render_as_batch=True` to support SQLite's limited `ALTER TABLE`.

## UI Features

| Feature             | Implementation                                              |
|---------------------|-------------------------------------------------------------|
| Dark mode           | `ui.dark_mode()` + `app.storage.user` (server-side per-session storage) for session persistence |
| Chart dark mode     | `views/chart_utils.py:apply_dark()` injects ECharts text colours |
| Budget period picker | 10 presets (This Month → Last 5 Years), `ui.refreshable` content |
| Categories CRUD     | Grouped by Income / Expense, inline edit & delete dialogs  |
| Keyboard shortcuts  | `Ctrl+N` = new transaction, `Enter` = submit              |
| CSV import          | Auto-detects delimiter, date format, debit/credit columns  |
| Internal transfers  | Auto-detection by amount ± tolerance within ±3 days        |
| Institutions CRUD   | Card grid at `/institutions`; add/edit/delete dialogs; type icons + hex colour per institution |
| Accounts grouping   | Toggle between group-by-Type and group-by-Institution; dynamic column swap via `_columns_for(by)`; institution selector in add/edit dialogs |
| Transaction filtering | Filter panel: date range, multi-select accounts/categories/types, description search; 50/page pagination with total count display |
| Split transactions  | `is_split` mode in add-transaction dialog; per-split category, amount, note; balance indicator; Fill Last button; auto-scroll on add row |
| Net Worth           | `/net-worth`: summary cards (assets/liabilities/net worth + monthly change), 13-month ECharts line+area chart (axis label colour overrides for dark mode), side-by-side assets/liabilities account table, physical assets CRUD section (Add/Edit/Delete dialogs); foreign-currency account rows show native and converted balances; all totals in default currency |
| Physical assets     | `Asset` model (`models/asset.py`): name, type (`AssetType`), current value, description, optional purchase date and price; `AssetService` provides full CRUD; values included in `total_assets` and net worth history via `NetWorthService` |
| Multi-currency      | Currency selector in Accounts add/edit dialogs; Settings page: default currency selector + per-currency manual exchange rate editor; Transfer dialog shows "To Account" selector and exchange rate panel for cross-currency pairs (rate or amount auto-calculation) |
| PWA                 | `pwa.py` registers `/manifest.json`, `/sw.js`, `/static`; `PWA_HEAD` injected via `ui.add_head_html()` on every page; service worker: cache-first static assets, network-first navigation, API calls bypass cache |
| Planned transactions | `/planned`: recurring income/expense/transfer with weekly/monthly/yearly frequency; optional end date or occurrence limit; active/inactive toggle; `PlannedTransactionService.active_occurrences_between()` used by transactions view (show-planned toggle) and forecast |
| Credit calculator   | `/credit-calculator`: stateless loan amortization for consumer loans, car loans, mortgages; equal vs decreasing installments; monthly overpayment or one-off lump-sum simulation; ECharts chart + amortization schedule table; no DB writes |
| Account balance forecast | `/forecast`: Prophet-based forecast per account or combined multi-account selection; configurable horizon; "include planned transactions" toggle; shaded confidence interval; zero-balance crossing alert; insufficient-history warning when fewer than 90 data points |
| Annual budget planning | `/budget-plan`: 12-column × N-category grid for a selected year; inline cell editing; "set uniform amount" and "copy previous month" bulk actions; "Budget vs Actual" toggle overlays real spending; year-over-year comparison; negative values rejected at schema level |
| Setup wizard        | `/wizard`: onboarding steps (institution → accounts with opening balances → categories → zero-based budget assignment); "Finish Setup" disabled until unassigned amount = 0; "load suggested categories" inserts a predefined set; wizard progress persists across sessions; fresh empty database redirects here automatically. `/setup` (separate) handles first-run database configuration |
| Settings            | `/settings`: 6 tabs — General (language, currency, date format, week start), Appearance (theme, sidebar default), Features (reset Getting Started; detector look-back windows for Subscriptions, Housekeeping, Payment Calendar), Data (backup/restore, seed, wipe — requires typing `DELETE`; exchange rates), History (audit log), About (version, env, links). All knobs persist in `app.storage.user`. |

## Development Tools

| Tool         | Purpose                              |
|--------------|--------------------------------------|
| pytest       | Unit and integration testing         |
| pytest-asyncio | Async test support (`asyncio_mode=auto`) |
| ruff         | Linting and formatting               |
| mypy         | Static type checking (strict mode)   |
| pytest-cov   | Code coverage reporting              |
| Faker        | Realistic Polish test/seed data      |

## Testing Strategy

Tests live in `tests/unit/` split into three layers:

- **`schemas/`** — Pydantic validation: valid inputs, boundary values, SQL injection payloads accepted verbatim, enum rejection
- **`services/`** — Service CRUD against in-memory SQLite (`aiosqlite`), ORM round-trip injection tests
- **`security/`** — Cross-cutting: SQL injection, XSS, path traversal, oversized inputs, enum field rejection, integer field rejection

All async tests use `async def` with `asyncio_mode = auto` (no `@pytest.mark.asyncio` needed).

## Deployment

| Tool           | Purpose                              |
|----------------|--------------------------------------|
| Docker         | Containerized deployment             |
| Podman         | Rootless container alternative       |
| docker-compose | Multi-service orchestration          |

## Runtime Modes

Set via `KALETA_MODE` environment variable:

| Mode    | Command                          | Description                          |
|---------|----------------------------------|--------------------------------------|
| `web`   | `uv run kaleta`                  | Browser-accessible web app (default) |
| `app`   | `KALETA_MODE=app uv run kaleta`  | NiceGUI native desktop window        |
| `api`   | `KALETA_MODE=api uv run kaleta`  | Headless REST API only               |

## Environment Configuration

```
KALETA_DB_URL=sqlite:///kaleta.db     # Database connection string
KALETA_HOST=0.0.0.0                   # Bind address
KALETA_PORT=8080                      # Bind port
KALETA_MODE=web                       # web | app | api
KALETA_SECRET_KEY=...                 # Session/auth secret (required for browser storage)
KALETA_DEBUG=false                    # Debug mode / hot reload
```
