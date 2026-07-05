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
    ┌──────▼──────────────────▼──────┐
    │   Views (NiceGUI) + REST API   │
    │      (pages / api/v1 routes)   │
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
│   │   ├── category.py      # UNIQUE(name, parent_id) constraint; is_subscriptions_root flag
│   │   ├── institution.py   # Institution model + InstitutionType enum
│   │   ├── asset.py         # Asset model + AssetType enum
│   │   ├── payee.py         # Payee model (name UNIQUE)
│   │   ├── planned_transaction.py  # PlannedTransaction model (frequency, end_date, occurrences)
│   │   ├── credit.py        # CreditCardProfile + LoanProfile (one-per-account, FK → accounts.id CASCADE)
│   │   └── mixins.py        # TimestampMixin
│   ├── schemas/             # Pydantic schemas (request/response)
│   │   ├── account.py
│   │   ├── transaction.py
│   │   ├── budget.py
│   │   ├── category.py
│   │   ├── institution.py
│   │   ├── asset.py
│   │   ├── planned_transaction.py
│   │   ├── credit.py        # CardView (utilization, min-payment, next-due, status chip) + LoanView (remaining balance, amortisation schedule)
│   │   └── wizard_projections.py  # PulledRow, BudgetBuilderProjection, PaymentCalendarProjection, SubscriptionCharge
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
│   │   ├── payee_service.py # Payee CRUD + merge() + find_or_create()
│   │   ├── subscription_service.py  # detect_candidates(window_days=...) — skips Subscriptions-tree transactions; create_from_candidate re-categorises history; subscription_transactions_grouped(window_days=90)
│   │   ├── dedupe_service.py        # duplicate_transactions(window_days=...) — configurable scan window
│   │   ├── planned_transaction_service.py  # grid_for_month(..., overdue_window_days=...) — configurable overdue look-back
│   │   ├── credit_service.py        # CreditService: card CRUD + loan CRUD; pure helpers: compute_monthly_payment, amortisation_schedule, compute_min_payment, next_due_date
│   │   └── wizard_projection_service.py  # WizardProjectionService: get_budget_builder_sources(year), get_payment_calendar_sources(start, end) — read-only cross-panel projections
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
│       ├── forecast.py      # Account balance forecast page (/forecast)
│       ├── institutions.py  # Institutions CRUD page (/institutions)
│       ├── net_worth.py     # Net Worth summary page (/net-worth)
│       ├── planned_transactions.py  # Planned/recurring transactions page (/planned)
│       ├── credit_calculator.py     # Loan amortization calculator (/credit-calculator)
│       ├── credit.py                # Credit module (/credit): two tabs — Credit Cards and Loans; "New card"/"New loan" dialogs atomically create Account + profile
│       ├── budget_plan.py           # Annual budget planning grid (/budget-plan)
│       ├── setup.py                 # First-run database setup page (/setup)
│       ├── settings.py              # Settings page (/settings) — 6 tabs; module docstring lists all app.storage.user keys
│       └── wizard.py                # Onboarding wizard (/wizard)
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

## Architecture Decision Records

Full ADR text lives in [`adr/`](adr/) — one file per decision. The
index below is in numeric order (021, 030, and 031 were recorded
out of sequence in the original monolithic document).

| ADR | Title | Status |
|-----|-------|--------|
| [001](adr/001-nicegui-as-ui-framework.md) | NiceGUI as UI Framework | accepted |
| [002](adr/002-sqlalchemy-20-with-dual-database-support.md) | SQLAlchemy 2.0 with Dual Database Support | accepted |
| [003](adr/003-mvc-service-layer-separation.md) | MVC + Service Layer Separation | accepted |
| [004](adr/004-pydantic-for-validation-settings.md) | Pydantic for Validation & Settings | accepted |
| [005](adr/005-rest-api-available-by-default.md) | REST API Available by Default | accepted |
| [006](adr/006-dockerpodman-deployment.md) | Docker/Podman Deployment | accepted |
| [007](adr/007-uv-as-package-manager.md) | uv as Package Manager | accepted |
| [008](adr/008-prophet-for-financial-forecasting.md) | Prophet for Financial Forecasting | accepted |
| [009](adr/009-per-user-settings-via-appstorageuser.md) | Per-User Settings via app.storage.user | accepted |
| [010](adr/010-budget-range-aggregation.md) | Budget Range Aggregation | accepted |
| [011](adr/011-institution-as-optional-account-grouping-entity.md) | Institution as Optional Account Grouping Entity | accepted |
| [012](adr/012-split-transactions-gnucash-style.md) | Split Transactions (GnuCash-style) | accepted |
| [013](adr/013-service-level-filtering-and-pagination-for-transactions.md) | Service-Level Filtering and Pagination for Transactions | accepted |
| [014](adr/014-net-worth-as-a-computed-view-with-no-dedicated-model.md) | Net Worth as a Computed View with No Dedicated Model | accepted |
| [015](adr/015-physical-assets-as-a-separate-model-from-bank-accounts.md) | Physical Assets as a Separate Model from Bank Accounts | accepted |
| [016](adr/016-multi-currency-accounts-and-cross-currency-transfers.md) | Multi-Currency Accounts and Cross-Currency Transfers | accepted |
| [017](adr/017-progressive-web-app-pwa-support.md) | Progressive Web App (PWA) Support | accepted |
| [018](adr/018-category-uniqueness-scoped-to-parent.md) | Category Uniqueness Scoped to Parent | accepted |
| [019](adr/019-payee-as-a-first-class-entity-with-merge-support.md) | Payee as a First-Class Entity with Merge Support | accepted |
| [020](adr/020-transfer-detection-via-counterparty-account-number-matching.md) | Transfer Detection via Counterparty Account Number Matching | accepted |
| [021](adr/021-bdde2e-test-layer-with-pytest-playwright.md) | BDD/E2E Test Layer with pytest-playwright | accepted |
| [022](adr/022-plannedrecurring-transactions-as-a-first-class-model.md) | Planned/Recurring Transactions as a First-Class Model | accepted |
| [023](adr/023-credit-calculator-as-a-stateless-pure-python-service.md) | Credit Calculator as a Stateless Pure-Python Service | accepted |
| [024](adr/024-account-balance-forecast-view-replaces-implicit-forecast-pag.md) | Account Balance Forecast View Replaces Implicit Forecast Page | accepted |
| [025](adr/025-annual-budget-planning-grid-with-year-navigation.md) | Annual Budget Planning Grid with Year Navigation | accepted |
| [026](adr/026-initial-setup-wizard-with-zero-based-budget-enforcement.md) | Initial Setup Wizard with Zero-Based Budget Enforcement | accepted |
| [027](adr/027-settings-page-with-tabbed-layout-and-user-configurable-servi.md) | Settings Page with Tabbed Layout and User-Configurable Service Parameters | accepted |
| [028](adr/028-subscriptions-category-tree-as-source-of-truth.md) | Subscriptions Category Tree as Source of Truth | accepted |
| [029](adr/029-credit-card-and-loan-profiles-as-separate-tables-extending-a.md) | Credit Card and Loan Profiles as Separate Tables Extending Account | accepted |
| [030](adr/030-read-only-cross-panel-projection-layer.md) | Read-Only Cross-Panel Projection Layer | accepted |
| [031](adr/031-sortablejs-drag-and-drop-for-dashboard-widget-reorder.md) | SortableJS Drag-and-Drop for Dashboard Widget Reorder | accepted |
| [032](adr/032-retire-the-controller-layer-views-call-services-directly.md) | Retire the Controller Layer — Views Call Services Directly | accepted |
| [033](adr/033-agpl-core-with-cla.md) | AGPL-3.0 Core with CLA and Proprietary Commercial Tier | accepted |

## UI Colour Schema

All UI tokens live in `src/kaleta/views/theme.py`. Dark mode is driven by NiceGUI's `ui.dark_mode()` (Quasar plugin), which adds the `dark` class to the `<html>` element — matching the Tailwind `dark:` variant strategy.

### Rules

**Do NOT use bare Quasar palette classes** (`bg-grey-1`, `border-grey-2`, `text-grey-7`, etc.) for structural chrome or text — they are fixed values that don't adapt in dark mode.  
**DO use Tailwind colour classes with explicit `dark:` variants**.

| Role | Light | Dark |
|---|---|---|
| Page background | `bg-slate-50` | `dark:bg-slate-950` |
| Card / surface | `bg-white/80` | `dark:bg-slate-900/70` |
| Card border | `border-slate-200/70` | `dark:border-slate-800` |
| Row hover | `hover:bg-slate-50` | `dark:hover:bg-slate-800/50` |
| Row divider | `border-slate-200` | `dark:border-slate-700` |
| Primary text | `text-slate-900` | `dark:text-slate-100` |
| Secondary / muted text | `text-slate-500` | `dark:text-slate-400` |
| Table header text | `text-slate-500` | `dark:text-slate-400` |
| Table cell text | `text-slate-800` | `dark:text-slate-200` |
| Subcategory label | `text-slate-700` | `dark:text-slate-200` |
| Highlight banner (blue) | `bg-blue-50` | `dark:bg-blue-900/40` |
| Info card (blue) | `bg-blue-50` | `dark:bg-blue-900/30` |

### Shared tokens (theme.py)

| Token | Purpose |
|---|---|
| `SECTION_CARD` | White card with border and shadow; adapts to dark |
| `TOOLBAR_CARD` | Compact version of SECTION_CARD for filter bars |
| `TABLE_SURFACE` | Applied to every `ui.table`; transparent bg + typed text colours |
| `BODY_MUTED` | Muted body copy; slate-500/slate-400 |
| `SECTION_TITLE` | Small all-caps label for section headers |
| `SECTION_HEADING` | Larger heading inside a card |
| `DIALOG_TITLE` | Bold title inside dialogs |
| `PAGE_TITLE` | Page-level h1 |

### Guidelines

- **All `ui.table` widgets must use `TABLE_SURFACE`** — it provides dark-mode cell text colours. Do not use plain `w-full` without TABLE_SURFACE.
- **Dialogs** created with `ui.dialog()` / `ui.card()` inherit Quasar's dark theme automatically. Do not set `bg-white` on dialog cards.
- **Info banners** with background colour must carry `dark:` variants (e.g. `bg-blue-50 dark:bg-blue-900/40`).
- **ECharts** do not auto-adapt to Quasar dark mode — always pass `is_dark` from `app.storage.user.get("dark_mode", False)` and apply via `views/chart_utils.py:apply_dark()`.
- **Semantic colours** (income = green, expense = red, transfer = blue) should use Tailwind classes (`text-green-600`, `text-red-600`) or Quasar colour props (`color="positive"`, `color="negative"`). Do not hard-code hex in CSS unless inside an ECharts series definition.
