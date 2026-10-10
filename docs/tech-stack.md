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
| Password hashing | argon2-cffi          | Login passwords and one-time recovery codes    |
| Second factor    | pyotp + qrcode       | TOTP (RFC 6238) and the enrolment QR as inline SVG |
| Column crypto    | cryptography         | AES-256-GCM for secrets at rest (`kaleta.db.types`) |

## Analytics & Forecasting

| Component        | Technology  | Purpose                                                       |
|------------------|-------------|---------------------------------------------------------------|
| Forecasting      | Prophet (optional `forecast` extra) or seasonal-naive fallback | 30–90 day cash flow forecasting with confidence band |
| Charts           | ECharts     | Budget vs actual, cash flow, forecast charts via `ui.echart` |

Install Prophet for advanced forecasting:

```bash
uv sync --extra forecast
```

Without the extra, the Forecast page uses a lightweight seasonal-naive projection
(same result schema: yhat / lower / upper) and shows an informational banner.
Both backends run CPU work in a thread pool via `asyncio.run_in_executor`.

## Bank statement import

| Component | Technology | Purpose |
|-----------|------------|---------|
| CSV / QIF / MT940 | stdlib (`csv`, `re`, `zipfile`) | Text statement formats; no dependency |
| XLSX | openpyxl (optional `import-xlsx` extra) | Excel statements; resolves Excel serial dates |

Install XLSX support:

```bash
uv sync --extra import-xlsx
```

Without the extra, uploading a workbook fails with a message naming the extra.
Every bank Kaleta supports also offers CSV, so XLSX is a convenience rather
than the only way in — which is why it is an extra and not a base dependency
(see [ADR-034](adr/034-openpyxl-as-an-optional-extra-for-xlsx-import.md)).

Profiles live in `services/import_profiles.py`; adding one needs a real
anonymized fixture first (`tests/e2e/fixtures/import/README.md`).

## Database

| Option           | Use Case                                      |
|------------------|-----------------------------------------------|
| SQLite (default) | Single-user, local, zero-config               |
| PostgreSQL (opt) | Self-hosted on Postgres, or the hosted multi-tenant layout (schema per account, ADR-35) |

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
| Credit module       | `/credit`: two tabs — Credit Cards and Loans. "New card" / "New loan" dialogs atomically create an `Account` (`type=CREDIT`) + the matching profile row. Cards show utilization bar (green < 30 %, amber < 70 %, red ≥ 70 %), min-payment (max(2 % × balance, 30 PLN) capped at balance), next-due date, and on-time / due-soon / overdue status chip. Loans show remaining balance and full amortisation schedule. Dashboard `credit_utilization` widget lists all card utilization bars (half-width card). |
| Account balance forecast | `/forecast`: Prophet when the `forecast` extra is installed, otherwise seasonal-naive fallback; per account or combined multi-account; configurable horizon; shaded confidence interval; model presets (Prophet only); what-if scenarios; planned-transaction overlay; insufficient-history warning when fewer than 14 distinct days |
| Annual budget planning | `/budget-plan`: 12-column × N-category grid for a selected year; inline cell editing; "set uniform amount" and "copy previous month" bulk actions; "Budget vs Actual" toggle overlays real spending; earlier years picked beside the edited one add their actuals as reference rows, and January shows last December's actual; negative values rejected at schema level |
| Setup wizard        | `/wizard`: onboarding steps (institution → accounts with opening balances → categories → zero-based budget assignment); "Finish Setup" disabled until unassigned amount = 0; "load suggested categories" inserts a predefined set; wizard progress persists across sessions; fresh empty database redirects here automatically. `/setup` (separate) handles first-run database configuration |
| Settings            | `/settings`: 6 tabs — General (language, currency, date format, week start), Appearance (theme, sidebar default), Features (reset Getting Started; detector look-back windows for Subscriptions, Housekeeping, Payment Calendar), Data (backup/restore, seed, wipe — requires typing `DELETE`; exchange rates), History (audit log), About (version, env, links). All knobs persist in `app.storage.user`. |
| Subscriptions panel | `/wizard/subscriptions`: "By category" card groups the last 90 days of charges under the Subscriptions category tree (root identified by `is_subscriptions_root=True`, v1 = flat root + direct children). Detector surfaces only un-categorised recurrences (transactions already in the tree are skipped). Confirming a candidate prompts for a sub-category and re-categorises all window-matching historical transactions (same payee or merchant-key + same amount bucket). "Manage categories" button links to `/categories`. |
| Cross-panel projections | `WizardProjectionService` computes read-only monthly-equivalent projections of each wizard panel's data. Budget Builder (`/wizard/budget-builder`) renders pulled rows (lock icon + source badge + cross-link) under Income / Fixed / Variable and lists reserve funds from the projection. Payment Calendar (`/payment-calendar`) merges subscription charges into day bubbles (count + outflow) and surfaces them in the day drawer with a subscription icon. Pulled rows are never stored on the consumer side; they are recomputed at render time from the source panel's authoritative data. |
| Dashboard Edit mode     | "Edit layout / Done" toggle on the dashboard header flips an editing state (body-class toggle, no Python round-trip). SortableJS drag-and-drop is wired to three size-isolated containers (`dash-kpi`, `dash-half`, `dash-full`); cross-size drops are rejected. Alt+↑/↓ keyboard reorder within a size group. Drop and keyboard moves POST to `/_dashboard/order`; order is merged by `_merge_order()` and written to `app.storage.user["dashboard_widgets"]`. Edit mode is not persisted — always starts locked on page load. Customize dialog retains checkboxes/Reset/Save; per-row arrows removed. |

## Client-side JS Dependencies

| Library    | Version | Licence | How loaded          | Purpose                                      |
|------------|---------|---------|---------------------|----------------------------------------------|
| SortableJS | 1.15.2  | MIT     | jsDelivr CDN (head) | Drag-and-drop widget reorder on the dashboard |

## Development Tools

Install dev tools with `uv sync --group dev` (not an optional extra). Run the full
DoD gate with `./scripts/verify.sh` (add `--e2e` when views change).

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
KALETA_DB_URL=sqlite+aiosqlite:///{home}/.kaleta/kaleta.db
KALETA_HOST=127.0.0.1                   # Bind address (Docker Compose sets 0.0.0.0)
KALETA_PORT=8080                      # Bind port
KALETA_MODE=web                       # web | app | api
KALETA_SECRET_KEY=...                 # Session/auth secret (required outside debug);
                                      # also derives the key for encrypted columns —
                                      # rotating it forces re-enrolling two-factor auth
KALETA_DEBUG=false                    # Debug mode; allows placeholder secret key
KALETA_API_TOKEN=...                  # Bootstrap bearer for headless API (≥16 chars);
                                      # creates locked user `api` on startup if needed
KALETA_SESSION_TTL_HOURS=72           # UI session TTL; 0 disables
KALETA_SESSION_IDLE_HOURS=12          # UI idle timeout; 0 disables, capped at TTL
KALETA_REDIS_URL=                     # Sessions + login rate limiter in Valkey/Redis, for more
                                      # than one replica (extra: hosted); unset = files + memory
```

### Tenancy layout (ADR-35, ADR-38)

```
KALETA_AUTH_BACKEND=local             # local (argon2, public.local_identities) | supabase (Supabase Auth)
                                      # | fake (debug stand-in for Supabase; KALETA_DEBUG only)
KALETA_SUPABASE_URL=                  # https://<project>.supabase.co — required for supabase
KALETA_SUPABASE_ANON_KEY=             # public anon key — required for supabase
KALETA_SUPABASE_SERVICE_ROLE_KEY=     # server-side only: admin calls (deleting an identity)
KALETA_PUBLIC_URL=                    # this instance's URL, for links in e-mails
```

Every instance uses one layout: the database is `KALETA_DB_URL` (no first-run
wizard, no `~/.kaleta/config.json`; `KALETA_TENANCY` is no longer read). A `public` registry (`tenants`, `tenant_members`,
`tenant_invites`, migrated by `alembic_public/`) names each account's schema
(`t_` + 12 random hex characters); tenant schemas are migrated by `alembic/`
with `-x tenant_schema=`. Every session is bound to the current tenant with
SQLAlchemy's `schema_translate_map` — never `SET search_path` — and a request
that has not resolved its tenant gets no session at all. API tokens are
`kt_<tenant>_<secret>` so the tenant is known before the token is looked up.
Scheduled backups, the NBP startup fetch (it returns per instance in part B2c)
and the integrity check no longer exist; the event retention sweep visits
every active family. Multi-tenant SQLite (every schema an attached file next
to the main one) exists for development and tests; production runs PostgreSQL.

On PostgreSQL each process keeps at most ten connections (`pool_size=5`,
`max_overflow=5`, pre-ping on) and asyncpg prepares no reusable statements,
so the app runs behind a transaction-mode pooler (Supabase, port 6543). On
startup the registry is migrated first, then each tenant schema; a schema that
fails is marked `suspended` and the rest start. `GET /api/v1/health` reports
`tenancy`, `auth_backend`, `tenants_pending_migration`, `suspended_tenants` and
`keyring_sessions` (unlocked sessions in this process, a count).
`KALETA_AUTH_BACKEND=fake` (`kaleta.auth.providers.fake`) confirms every
address at sign-up and keeps argon2 hashes in `~/.kaleta/fake-auth.json`; it
drives `compose.hosted-dev.yml` and is refused without `KALETA_DEBUG=true`.
Operator scripts: `migrate_tenants.py` (deploy hook), `tenant_admin.py`
(list, members, suspend, resume, delete), `hosted_smoke.sh` (post-deploy
smoke) and `reset_demo.py --tenant` (the demo as an account).

### Field-level encryption

```
KALETA_ENCRYPTION=passphrase          # passphrase (default, always on) | off
                                      # off is refused unless KALETA_DEBUG
KALETA_DATA_PASSPHRASE=               # scripts only (seed.py, reset_demo.py);
                                      # prompted when unset
```

When `passphrase` is on, every user-written text column — account,
payee, category, tag and institution names, transaction descriptions
and notes, payee contact fields, saved reports, rule patterns and more
— is stored as ciphertext (`EncryptedText`: AES-256-GCM, a format byte,
a key-version byte, a 12-byte nonce, AAD of `table.column`). With
encryption off the same columns hold a `\x00` format byte and UTF-8
plaintext, so a database can be switched on later without a schema
change.

Keys come from a three-layer hierarchy, built on `cryptography` and
`argon2-cffi`: a member's data passphrase stretches through Argon2id
(`t=3, m=64 MiB, p=1`, parameters stored per member) into a
key-encryption key that unwraps an X25519 private key, which opens the
account's AES-256 data key (DEK) sealed to that member's public key. A
26-character Crockford base32 recovery code wraps the private key a
second time. Equality and uniqueness use `_bidx` columns — an HMAC of
the normalised value, keyed from the DEK via HKDF, stored next to the
ciphertext — so unique names and account-number matching keep working
without decrypting rows in SQL.

Search and sort over encrypted text run in Python rather than SQL
(`ILIKE` cannot see into ciphertext). Measured on 50 000 encrypted
transactions: a search page + count takes ≈100–125 ms on SQLite and
≈80–100 ms on Postgres 16, against a 300 ms budget (the page's scan is
reused for its count within one session).

See [privacy.md](privacy.md#encryption) for what this protects against
and [ADR-35](adr/035-hosted-multi-tenancy-and-user-held-encryption.md)
for the full design. For data written before encryption was on, see
[deployment.md](deployment.md#encrypting-data-that-predates-encryption).

### Observability and bug reports

```
KALETA_LOG_FORMAT=text                # text (terminal) | json (one object per line)
KALETA_LOG_LEVEL=INFO                 # Python level name; KALETA_DEBUG=true forces DEBUG
KALETA_EVENTS_ENABLED=true            # Anonymous error events (docs/privacy.md)
KALETA_EVENT_RETENTION_DAYS=7         # Rolling deletion window for events
KALETA_BUG_REPORTS_ENABLED=true       # In-app "Report a problem" retention reaper
KALETA_BUG_REPORT_RETENTION_DAYS=90   # Rolling deletion window for filed reports
KALETA_BUG_REPORT_WEBHOOK=            # POST each report as JSON (n8n, generic endpoint)
KALETA_BUG_REPORT_WEBHOOK_INCLUDE_LOGS=false  # Include the log excerpt in that POST
KALETA_BUG_REPORT_EMAIL=              # Also e-mail reports (needs the SMTP settings)
KALETA_SMTP_HOST=                     # SMTP relay for report e-mail
KALETA_SMTP_PORT=587
KALETA_SMTP_USERNAME=
KALETA_SMTP_PASSWORD=
KALETA_SMTP_FROM=                     # Envelope sender; defaults to the username
KALETA_SMTP_STARTTLS=true
KALETA_ERROR_TRACKER_DSN=             # Optional Sentry-protocol endpoint (extra: tracker)
```

`KALETA_LOG_FORMAT=json` adds `request_id`, `session_id`, `route`, `event_id`
and `app_version` to every line, so the ID a user reads off an error leads to
the lines around it. Records are redacted (bearer tokens, e-mail addresses,
query strings, over-long arguments) before any handler writes them, and the
last 200 lines of a session are held in memory so a bug report can attach them
— only when the user ticks the box. See [privacy.md](privacy.md).

Scheduled backups are SQLite file snapshots (`VACUUM INTO`), separate from the
Settings → Data ZIP export/restore format. They are a no-op for PostgreSQL and
in-memory SQLite.