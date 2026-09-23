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
│   │   ├── session.py       # Session factory, dependency
│   │   ├── types.py         # EncryptedString(TypeDecorator): AES-256-GCM over LargeBinary, key via HKDF-SHA256 from KALETA_SECRET_KEY (swappable key source)
│   │   └── audit.py         # Audit log capture; _SKIP_TABLES excludes tables with encrypted secrets (e.g. user_mfa)
│   ├── models/              # SQLAlchemy ORM models
│   │   ├── account.py
│   │   ├── transaction.py   # Transaction + TransactionSplit models
│   │   ├── budget.py
│   │   ├── category.py      # UNIQUE(name, parent_id, type) constraint; is_subscriptions_root flag
│   │   ├── institution.py   # Institution model + InstitutionType enum
│   │   ├── asset.py         # Asset model + AssetType enum
│   │   ├── payee.py         # Payee model (name UNIQUE)
│   │   ├── planned_transaction.py  # PlannedTransaction model (frequency, end_date, occurrences)
│   │   ├── credit.py        # CreditCardProfile + LoanProfile (one-per-account, FK → accounts.id CASCADE)
│   │   ├── user_mfa.py      # UserMfa: TOTP secret (EncryptedString), recovery code hashes, replay counter
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
│   │   ├── wizard_projections.py  # PulledRow, BudgetBuilderProjection, PaymentCalendarProjection, SubscriptionCharge
│   │   └── auth.py          # MfaStatusResponse — read-only two-factor status
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
│   │   ├── wizard_projection_service.py  # WizardProjectionService: get_budget_builder_sources(year), get_payment_calendar_sources(start, end) — read-only cross-panel projections
│   │   └── mfa_service.py   # MfaService: TOTP enrolment/verification (replay-guarded), recovery codes, disable
│   ├── api/                 # REST API endpoints (v1/); v1/auth.py exposes GET /api/v1/auth/mfa (status only)
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
│       ├── settings/                # Settings page (/settings) — one module per tab
│       ├── login_mfa.py             # TOTP challenge page (/login/mfa); public route, guards itself
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
│   └── seed.py              # thin CLI over src/kaleta/seeders/
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
| [018](adr/018-category-uniqueness-scoped-to-parent.md) | Category Uniqueness Scoped to Parent and Type | accepted |
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
| [034](adr/034-openpyxl-as-an-optional-extra-for-xlsx-import.md) | openpyxl as an Optional Extra for XLSX Import | accepted |
| [035](adr/035-hosted-multi-tenancy-and-user-held-encryption.md) | Hosted Multi-Tenancy: Schema per Account and User-Held Field Encryption | proposed |
| [036](adr/036-local-column-encryption-and-totp-as-base-dependencies.md) | Local Column Encryption and TOTP as Base Dependencies | accepted |

## UI Colour Schema

All UI tokens live in `src/kaleta/views/theme.py`. The visual language is the
"sand" palette from `docs/design/restyle/README.md`: warm paper, deep ink,
apricot accent, forest/terracotta for money in and out. Typography is
self-hosted **Libre Franklin** for UI text and **IBM Plex Mono** for every
number (`static/fonts/`, both SIL OFL). Dark mode is driven by NiceGUI's
`ui.dark_mode()` (Quasar plugin), which adds `body--dark` to `<body>`.

### Rules

**Do NOT use bare Quasar or Tailwind palette classes** (`bg-grey-1`,
`text-green-7`, `text-teal-600`, …) for structural chrome, text or figures.

**DO use the `.k-*` classes and shared constants from `theme.py`.** Each one
reads a CSS custom property, so it is written once and follows the mode.

Every colour is a custom property declared on `:root` and re-declared on
`.body--dark` — a `.k-*` class never needs a second dark-mode copy.

| Token | Light | Dark | Used for |
|---|---|---|---|
| `--k-ground` | `#F3EFE7` | `#171613` | body and drawer background |
| `--k-surface` | `#FCFAF6` | `#201F1A` | cards, header bar, table bodies |
| `--k-surface-sunken` | `#F3EFE7` | `#2A2822` | inset chips and mini-panels |
| `--k-ink` / `--k-ink-2` | `#1C1A15` / `#4A443A` | `#F0EBDF` / `#CFC7B6` | headings / body copy |
| `--k-muted` / `--k-muted-strong` | `#6B6353` / `#6E6656` | `#A8A08D` / `#A19781` | captions / eyebrows |
| `--k-hairline` / `--k-border` | `#EDE7DA` / `#E2DBCC` | `#2A2822` / `#322F27` | row dividers / card edges |
| `--k-accent` / `--k-accent-text` | `#B4591F` / `#9A4E1F` | `#E8935B` | accent surfaces / links |
| `--k-income` / `--k-expense` | `#36684D` / `#A44631` | `#6FAF87` / `#DE8672` | money in / out |
| `--k-warning` | `#8A5A12` | `#E3B457` | at-risk state |
| `--k-card-shadow` | `0 1px 2px rgba(28,26,21,.05)` | `none` | the only shadow in the system |

Quasar brand variables follow the same palette: `--q-primary: #B4591F`
(`#E8935B` dark), `--q-positive: #36684D`, `--q-negative: #A44631`.

### Shared classes and constants (theme.py)

| Token | Purpose |
|---|---|
| `SECTION_CARD` / `TOOLBAR_CARD` | Paper panel on ground — `.k-surface`, 1px shadow, no border |
| `TABLE_SURFACE` | `.k-table`; applied to every `ui.table` |
| `PAGE_TITLE` / `SECTION_HEADING` / `SECTION_TITLE` | 32px light ink title, 500-weight heading, eyebrow |
| `AMOUNT_*` / `amount_class()` | `.k-amount` — IBM Plex Mono, tabular figures, income/expense colour |
| `MONO` | `.k-mono` for non-amount numbers (dates, counts, the version string) |
| `KPI_VALUE` / `KPI_TREND_*` | KPI typography and `.k-trend--pos/neg/warn/neutral` |
| `ACCENT_SURFACE` / `ON_ACCENT` | Filled accent banner and the text colour that sits on it |
| `NAV_ITEM_ACTIVE` | Active sidebar route — paper card, ink label, accent icon |
| `.k-pace*` / `.k-filter-chip*` | Shared pace bar and filter chip primitives |
| `theme_css()` | Fonts + tokens + `DARK_CSS` |

### Guidelines

- **The accent (`text-primary`, `color=primary`) is for actions** — links,
  "Open →", active nav icons. It must not colour headings or figures; those
  are ink (`.k-heading`), and amounts use `amount_class()`.
- **Every number is monospace.** Amounts get `AMOUNT_*`; other figures get
  `MONO`, both with `font-variant-numeric: tabular-nums` so columns align.
- **ECharts** series colours live in `views/chart_utils.py` (`CHART_PALETTE`,
  `chart_palette(is_dark)`, `CHART_INK`, `CHART_ACCENT`, …); always pass
  `is_dark` and call `apply_dark()`.
- **KPI trend rows** use `KpiPeriodDelta` from `ReportService` and
  `format_kpi_trend()` in `dashboard_widgets/helpers.py`.
