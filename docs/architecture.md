# Kaleta - Architecture Decision Record

## Project Overview

**Kaleta** (Polish: leather money pouch) is a personal budget and finance management
application. It provides budgeting, transaction tracking, CSV import, cash flow forecasting,
and category management.

## Architecture Pattern: MVC + Service Layer

```
┌─────────────────────────────────────────────────┐
│                   Clients                        │
│         (Browser / Mobile / API Consumer)        │
└──────────┬──────────────────┬────────────────────┘
           │                  │
    ┌──────▼──────┐   ┌──────▼──────┐
    │  NiceGUI    │   │  REST API   │
    │  (Views)    │   │  (FastAPI)  │
    └──────┬──────┘   └──────┬──────┘
           │                  │
    ┌──────▼──────────────────▼──────┐
    │        Controllers             │
    │   (Request handling, routing)  │
    └──────────────┬─────────────────┘
                   │
    ┌──────────────▼─────────────────┐
    │         Services               │
    │   (Business logic layer)       │
    └──────────────┬─────────────────┘
                   │
    ┌──────────────▼─────────────────┐
    │         Models + Schemas       │
    │  (SQLAlchemy ORM + Pydantic)   │
    └──────────────┬─────────────────┘
                   │
    ┌──────────────▼─────────────────┐
    │         Database               │
    │   (SQLite default / PostgreSQL)│
    └────────────────────────────────┘
```

## Directory Structure

```
kaleta/
├── src/kaleta/
│   ├── __init__.py          # Package root, version
│   ├── main.py              # Application entrypoint
│   ├── pwa.py               # PWA setup: manifest, service worker, static routes, PWA_HEAD
│   ├── static/              # Static assets served at /static
│   │   ├── manifest.json    # Web App Manifest (name, display: standalone, theme_color)
│   │   ├── sw.js            # Service worker (cache-first static, network-first nav, bypass API)
│   │   └── icons/
│   │       └── icon.svg     # SVG wallet icon
│   ├── config/              # App configuration, settings
│   │   └── settings.py      # Pydantic settings (env-based)
│   ├── db/                  # Database setup, session management
│   │   ├── base.py          # SQLAlchemy base, engine
│   │   └── session.py       # Session factory, dependency
│   ├── models/              # SQLAlchemy ORM models
│   │   ├── account.py
│   │   ├── transaction.py   # Transaction + TransactionSplit models
│   │   ├── budget.py
│   │   ├── category.py      # UNIQUE(name, parent_id) constraint
│   │   ├── institution.py   # Institution model + InstitutionType enum
│   │   ├── asset.py         # Asset model + AssetType enum
│   │   ├── payee.py         # Payee model (name UNIQUE)
│   │   └── mixins.py        # TimestampMixin
│   ├── schemas/             # Pydantic schemas (request/response)
│   │   ├── account.py
│   │   ├── transaction.py
│   │   ├── budget.py
│   │   ├── category.py
│   │   ├── institution.py
│   │   └── asset.py
│   ├── services/            # Business logic
│   │   ├── account_service.py
│   │   ├── transaction_service.py
│   │   ├── budget_service.py
│   │   ├── category_service.py
│   │   ├── import_service.py
│   │   ├── report_service.py
│   │   ├── forecast_service.py
│   │   ├── institution_service.py
│   │   ├── asset_service.py
│   │   ├── net_worth_service.py
│   │   └── payee_service.py # Payee CRUD + merge() + find_or_create()
│   ├── controllers/         # Route handlers, orchestration
│   ├── api/                 # REST API endpoints (v1/)
│   └── views/               # NiceGUI UI pages
│       ├── layout.py        # Shared layout, nav, dark mode toggle
│       ├── chart_utils.py   # ECharts dark mode helpers
│       ├── dashboard.py
│       ├── transactions.py
│       ├── accounts.py
│       ├── categories.py
│       ├── budgets.py
│       ├── import_view.py
│       ├── forecast.py
│       ├── institutions.py  # Institutions CRUD page (/institutions)
│       └── net_worth.py     # Net Worth summary page (/net-worth)
├── tests/
│   ├── conftest.py          # In-memory SQLite async fixtures
│   ├── unit/
│   │   ├── schemas/         # Pydantic validation tests
│   │   ├── services/        # Service layer tests
│   │   └── security/        # SQL injection, XSS, input security
│   ├── integration/
│   └── e2e/                 # Playwright browser tests (pytest-playwright)
│       └── conftest.py      # base_url fixture; requires live app on :8080
├── scripts/
│   └── seed.py              # 6-year fake data generator (Faker pl_PL)
├── docs/
│   └── bdd.md               # BDD scenarios (Gherkin) for e2e tests
├── alembic/                 # Database migrations
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## Key Architecture Decisions

### ADR-001: NiceGUI as UI Framework
- **Decision**: Use NiceGUI for the web frontend.
- **Rationale**: Python-native, builds on FastAPI/Starlette, supports both web and
  desktop (app) mode, no need for separate JS frontend.
- **Consequence**: API layer comes "for free" since NiceGUI wraps FastAPI.

### ADR-002: SQLAlchemy 2.0 with Dual Database Support
- **Decision**: Use SQLAlchemy ORM with SQLite as default, PostgreSQL as optional.
- **Rationale**: SQLAlchemy's dialect system makes swapping backends trivial.
  SQLite is zero-config for personal use. PostgreSQL for multi-user / production.
- **Consequence**: Must avoid SQLite-incompatible features in models (e.g., array types).
  Use Alembic with `render_as_batch=True` for migrations that work across both backends.
  Enum columns use `SAEnum(..., native_enum=False)` for SQLite compatibility.

### ADR-003: MVC + Service Layer Separation
- **Decision**: Strict separation between Models, Views, Controllers, and Services.
- **Rationale**: Clean separation of concerns enables independent testing, reuse
  of business logic across UI and API, and easier future changes.
- **Consequence**: Slightly more files/boilerplate, but much better maintainability.

### ADR-004: Pydantic for Validation & Settings
- **Decision**: Use Pydantic v2 for request/response schemas and app configuration.
- **Rationale**: Type-safe validation, serialization, and env-based settings.
  Integrates natively with FastAPI (and thus NiceGUI).

### ADR-005: REST API Available by Default
- **Decision**: Expose a REST API alongside the UI.
- **Rationale**: Enables external integrations, mobile apps, automation scripts,
  and headless usage. Since NiceGUI uses FastAPI, API routes are easy to add.

### ADR-006: Docker/Podman Deployment
- **Decision**: Provide container-first deployment with Docker and Podman support.
- **Rationale**: Consistent environment, easy self-hosting, works on any platform.

### ADR-007: uv as Package Manager
- **Decision**: Use `uv` for dependency management and project tooling.
- **Rationale**: Fast, modern Python package manager. Handles venv creation,
  dependency resolution, and script running.

### ADR-008: Prophet for Financial Forecasting
- **Decision**: Use Meta's Prophet library for time-series forecasting.
- **Rationale**: Prophet handles seasonality, holidays, and missing data well — making
  it a natural fit for forecasting monthly expenses, income trends, and budget projections.
  Simple API with Pydantic-friendly outputs.
- **Consequence**: Forecasting logic lives in `services/forecast_service.py`.
  Prophet is CPU-bound; runs in a thread pool via `asyncio.run_in_executor` to avoid
  blocking the async event loop.

### ADR-009: Dark Mode via app.storage.user
- **Decision**: Store dark mode preference server-side in `app.storage.user`.
- **Rationale**: `app.storage.browser` (cookie-based) is not available synchronously
  on page render in NiceGUI. `app.storage.user` is server-side per-session and
  available immediately, making it reliable for per-page layout decisions.
- **Consequence**: Dark mode persists within a session but resets on server restart.
  ECharts charts have explicit colour overrides via `views/chart_utils.py:apply_dark()`
  since ECharts does not auto-adapt to Quasar's dark mode.

### ADR-010: Budget Range Aggregation
- **Decision**: `BudgetService.range_summary(start, end)` aggregates budget rows
  across multiple months using a scalar month key (`year * 12 + month`).
- **Rationale**: Budgets are stored per-month. To display multi-month ranges
  (quarter, year, last N days), budget amounts must be summed across all months that
  fall within the range, while actuals are filtered by exact transaction dates.
- **Consequence**: The UI period selector supports 10 presets (This Month → Last 5 Years).
  `monthly_summary()` now delegates to `range_summary()` to avoid duplication.

### ADR-011: Institution as Optional Account Grouping Entity
- **Decision**: Introduce an `Institution` model that accounts optionally reference via a nullable `institution_id` FK with `ON DELETE SET NULL`.
- **Rationale**: Users hold accounts at multiple financial institutions (banks, fintechs, brokers, etc.). Grouping accounts by institution is a natural mental model and a frequently needed view. Making the relationship optional preserves backwards compatibility — existing accounts require no migration data entry.
- **Consequence**: `Account` gains `institution_id` (nullable) and an `institution` relationship. Deleting an institution unlinks its accounts rather than cascading deletion. The accounts view gains a toggle to group by Type or by Institution. `InstitutionService` provides full CRUD with eager-loading via `selectinload` for the accounts relationship. `InstitutionType` uses `SAEnum(..., native_enum=False)` for SQLite compatibility, consistent with the rest of the codebase.

### ADR-012: Split Transactions (GnuCash-style)
- **Decision**: Add a `TransactionSplit` child model. A `Transaction` with `is_split=True` carries one or more `TransactionSplit` rows that each hold a `category_id`, `amount`, and optional `note`. The parent transaction's category is unused when splits are present.
- **Rationale**: Single-category transactions cannot represent real-world receipts that span multiple budget categories (e.g., a supermarket run covering groceries, household, and personal care). GnuCash's split model is the established pattern for this.
- **Consequence**: `Transaction` gains `is_split: bool` and a `splits` relationship. `TransactionSplitCreate` validates that splits are present when `is_split=True`. `TransactionService.create()` uses `flush()` to obtain the transaction `id` before writing split rows. `get()` and `list()` eager-load splits with their category. The Alembic migration is `c4f9e2b1a837_add_transaction_splits.py`. The add-transaction dialog in the UI toggles split mode with a balance indicator and a Fill Last button.

### ADR-013: Service-Level Filtering and Pagination for Transactions
- **Decision**: `TransactionService.list()` accepts `account_ids`, `category_ids`, `tx_types`, `date_from`, `date_to`, `search`, `offset`, and `limit` (default 50). A companion `TransactionService.count()` method accepts the same filter parameters and returns the total matching row count.
- **Rationale**: Returning all transactions in one query is impractical as history grows. Placing filter and pagination logic in the service keeps controllers and views thin and makes the same capability available to both the UI and the REST API. Providing a separate `count()` method avoids fetching full rows just for pagination metadata.
- **Consequence**: Multiple values within the same filter field use OR logic; different filter fields combine with AND. The transactions UI exposes a filter panel (date range, multi-select accounts/categories/types, description search) and a pagination control that shows total count.

### ADR-014: Net Worth as a Computed View with No Dedicated Model
- **Decision**: Net worth data is computed entirely at query time by `NetWorthService.get_summary()`. No `NetWorth` or `Snapshot` ORM model is added. Historical monthly values are reconstructed by walking backwards from current account balances, subtracting each month's net income/expense (internal transfers excluded).
- **Rationale**: Storing pre-computed snapshots would require either a background job or hook into every transaction write to stay consistent. For a personal-scale dataset the retrospective reconstruction from existing `Account` and `Transaction` data is fast enough and eliminates a synchronisation concern entirely.
- **Consequence**: `NetWorthService` depends only on existing models and produces three pure-Python dataclasses (`AccountSnapshot`, `MonthlyNetWorth`, `NetWorthSummary`) — no new migration is required. Account classification (asset vs. liability) is derived from balance sign: positive balance = asset, negative balance = liability. The view at `/net-worth` renders summary cards, a 13-month ECharts line+area chart coloured by sign, and a side-by-side account breakdown table.

### ADR-015: Physical Assets as a Separate Model from Bank Accounts
- **Decision**: Introduce a standalone `Asset` model (table `assets`) for physical, non-liquid assets such as real estate, vehicles, and valuables. Physical assets are not represented as `Account` rows.
- **Rationale**: Bank accounts have transaction history, balances derived from ledger entries, and institution relationships. Physical assets have none of these: their value is a single user-supplied figure, optionally paired with a purchase date and purchase price for gain/loss context. Forcing them into the `Account` model would require nullable columns for transaction-irrelevant fields and special-casing throughout the transaction, import, and budget logic. A dedicated model keeps both concepts clean.
- **Consequence**: `Asset` has fields `name`, `type` (`AssetType`: `REAL_ESTATE`, `VEHICLE`, `VALUABLES`, `OTHER`), `value` (Decimal), `description`, `purchase_date` (optional), and `purchase_price` (optional). `AssetType` uses `SAEnum(..., native_enum=False)` for SQLite compatibility. `AssetService` provides full CRUD (`list`, `get`, `create`, `update`, `delete`). `NetWorthService.get_summary()` loads physical assets via `_load_physical_assets()` and exposes them as `PhysicalAssetSnapshot` dataclasses inside `NetWorthSummary`. `total_assets` includes `total_physical_assets`; the monthly history reconstruction adds the physical asset total to the running net worth baseline. The net worth page gains an Add/Edit/Delete CRUD section for physical assets. The migration is `alembic/versions/d7a3e1f2b8c5_add_assets.py`.

### ADR-016: Multi-Currency Accounts and Cross-Currency Transfers
- **Decision**: Each `Account` carries a `currency` field (3-char ISO 4217 code, `VARCHAR(3) NOT NULL DEFAULT 'PLN'`). Each `Transaction` carries a nullable `exchange_rate` field (`NUMERIC(15,6)`), storing dest_currency per 1 src_currency for cross-currency transfers. `TransactionService.create_transfer(outgoing, incoming)` atomically creates both legs with linked IDs. `NetWorthService.get_summary(rates, default_currency)` accepts a `rates` dict (`currency → Decimal`) and converts all account balances to the user's default currency before aggregation.
- **Rationale**: Users holding accounts in multiple currencies need balances and net worth totals expressed in a single reporting currency. Storing the exchange rate on the transaction preserves the historical rate at the time of transfer, which would otherwise be lost if only a rates table were kept. Atomically creating both transfer legs in one service call prevents orphaned half-transfers.
- **Consequence**: The migration `alembic/versions/a1b2c3d4e5f6_add_currency_and_exchange_rate.py` adds `accounts.currency` and `transactions.exchange_rate`. The Settings page exposes a default currency selector and per-currency manual rate editor. The Accounts add/edit dialog includes a currency selector. The Transactions page shows a "To Account" selector when Transfer type is chosen, and an exchange rate panel for cross-currency transfers (enter rate OR source+destination amounts; the remaining field auto-calculates). The Net Worth page displays each foreign-currency account row with native balance alongside the converted balance, and all summary totals in the default currency.

### ADR-017: Progressive Web App (PWA) Support
- **Decision**: Add PWA support via `src/kaleta/pwa.py`, which registers `/manifest.json`, `/sw.js`, and `/static` endpoints on the NiceGUI/FastAPI app. `PWA_HEAD` (meta tags + service worker registration script) is injected via `ui.add_head_html()` in every page. `pwa.setup()` runs in `main.py` before views register, for both `web` and `app` modes.
- **Rationale**: PWA support allows Kaleta to be installed on mobile and desktop as a standalone app without a separate native build. The service worker uses cache-first for static assets and network-first for navigation; API calls bypass the cache entirely to keep financial data fresh.
- **Consequence**: Static files live in `src/kaleta/static/` (manifest, service worker, SVG icon). The `pwa` module owns all PWA-related routes and keeps them out of `main.py` and individual views.

### ADR-018: Category Uniqueness Scoped to Parent
- **Decision**: Replace the `UNIQUE(name)` constraint on `categories` with `UNIQUE(name, parent_id)` (`uq_categories_name_parent`).
- **Rationale**: The previous global uniqueness constraint prevented the same category name from appearing under different parent categories (e.g., "Other" under both "Food" and "Transport"). Scoping uniqueness to `(name, parent_id)` reflects how users actually organise hierarchical categories, where name collisions across different parents are valid and expected.
- **Consequence**: The migration is `alembic/versions/e3f4a5b6c7d8_categories_unique_name_parent.py`. Two top-level categories (both with `parent_id = NULL`) that share a name remain disallowed, since NULL = NULL in this context uses the constraint's composite key behaviour.

### ADR-019: Payee as a First-Class Entity with Merge Support
- **Decision**: Introduce a `Payee` model (`payees` table, `name UNIQUE`) and a `PayeeService` with full CRUD, `find_or_create()`, and `merge(keep_id, merge_ids)`. Transactions gain a nullable `payee_id` FK. During mBank CSV import, `ImportService.to_transaction_creates_with_payees()` resolves payee names via `find_or_create()`.
- **Rationale**: Payee names in bank exports are often inconsistent (truncated, all-caps, with bank reference suffixes). A deduplicated `Payee` entity allows users to merge duplicates into a canonical record, after which all historical transactions automatically reflect the merged payee. Separating payee identity from transaction descriptions enables cleaner reporting and future rule-based auto-categorisation.
- **Consequence**: `PayeeService.merge()` bulk-reassigns transactions from the merged payees to the kept payee using a single `UPDATE` statement, then deletes the redundant rows. `find_or_create()` uses `flush()` rather than `commit()` so that the caller owns the transaction boundary. The migration is `alembic/versions/d2e3f4a5b6c7_add_payees.py`.

### ADR-020: Transfer Detection via Counterparty Account Number Matching
- **Decision**: During mBank CSV import, `ImportService.to_transaction_creates_with_payees()` marks a row as `TRANSFER` (with `is_internal_transfer=True`) only when the row's `Numer rachunku` field (digits-only) appears in the caller-supplied `known_account_digits` set — the digit-normalised `external_account_number` values of the user's own accounts.
- **Rationale**: Generic heuristics (description keyword matching, amount pairing) produce false positives. Matching against the literal counterparty account number is deterministic and requires no fuzzy logic. Using a `known_account_digits` parameter keeps the import service stateless with respect to account data; the caller queries and passes the set.
- **Consequence**: Rows whose counterparty account is not in `known_account_digits` are classified as normal income/expense. After import, `ImportService.detect_and_link_transfers()` can pair unlinked `TRANSFER` legs across accounts (same amount ± tolerance, dates within `max_days_apart`) and write `linked_transaction_id` on both rows.

### ADR-021: BDD/E2E Test Layer with pytest-playwright
- **Decision**: Add a `tests/e2e/` layer using pytest-playwright. Tests run against a live Kaleta instance (default `http://localhost:8080`). The Gherkin-style scenarios driving the suite are documented in `docs/bdd.md`.
- **Rationale**: Unit and integration tests cover service logic and schema validation in isolation but cannot catch regressions in UI flow, page routing, or NiceGUI component wiring. Playwright-based e2e tests exercise the full stack from the browser, covering the same user journeys described in the BDD scenarios.
- **Consequence**: The app must be running before the e2e suite executes. Browsers must be installed once with `uv run playwright install chromium`. E2e tests are kept in a separate directory so they are not picked up by the default `uv run pytest` invocation (which targets unit/integration). The `tests/e2e/conftest.py` provides the `base_url` session fixture.
