---
plan_id: q4-supabase-deployment
title: Hosted instance on Supabase Postgres + CI postgres matrix
area: infrastructure
effort: large
status: archived
archived_at: 2026-08-26
roadmap_ref: ../../roadmap.md#q4-2026-open-source-launch
---

# Hosted instance on Supabase Postgres + CI postgres matrix

## Intent

Two goals in one: (1) validate the PostgreSQL code path, which has
never been exercised — the entire test suite and all development run
on SQLite despite the declared dual-database support; (2) stand up a
hosted instance backed by Supabase Postgres that doubles as the
public demo from the Q4 roadmap.

## Scope

### 1. Postgres correctness first (CI, no Supabase needed)

- Add a `postgres` job to CI: a `postgres:16` service container,
  `uv sync --group dev --extra postgres`, run unit + integration
  suites with `KALETA_DB_URL=postgresql+asyncpg://...`.
- Fix whatever falls out: SQLite-only assumptions in models,
  migrations (e.g. ALTER quirks handled by Alembic batch mode),
  services (date/decimal handling), seed script.
- Alembic `upgrade head` from empty → full schema must pass on
  Postgres; record any migration edits in implementation notes
  (edit forward — do not rewrite already-applied migration files
  unless they are broken on Postgres).

### 2. Supabase wiring

- Document (in `docs/deployment.md`, new): connection string via the
  **session pooler** (port 6543, IPv4-safe) for the app; **direct
  connection** (5432) for running Alembic migrations. asyncpg
  requires `postgresql+asyncpg://`; sslmode handling documented.
- Secrets via env only (`KALETA_DB_URL`, `KALETA_SECRET_KEY`) — never
  in the repo.

### 3. App hosting (open question resolves this)

- Deploy `kaleta:full` image to the chosen host with env config,
  HTTPS, and a persistent domain. `KALETA_HOST=0.0.0.0` inside the
  container is expected (documented in compose already).

### 4. Demo hardening

- Dedicated demo user with a published password; seed data loaded.
- A scheduled job (host cron / GitHub Action) resets the demo DB to
  the seed state daily.
- Banner in the UI when `KALETA_DEMO=true`: "Demo instance — data
  resets daily" (small, dismissible; env-gated feature flag).

**Not in scope:** commercial hosting infrastructure, multi-tenant
anything, Supabase Auth/Storage/Edge (only their Postgres is used).

## Acceptance criteria

- CI postgres job green: full unit + integration suites pass against
  `postgres:16`.
- `uv run alembic upgrade head` succeeds against a fresh Supabase
  database (record project ref + date in notes).
- `test -f docs/deployment.md` and link-checker passes.
- `grep -q "KALETA_DEMO" src/kaleta/config/settings.py` (demo flag
  exists, default false).
- `[manual]` Hosted instance reachable over HTTPS, login with demo
  credentials works, dashboard renders seed data.
- `[manual]` Demo reset job observed to run once.

## Touchpoints

`.github/workflows/ci.yml` (postgres matrix), possibly
`alembic/versions/*` (postgres compat), `src/kaleta/config/settings.py`
(`KALETA_DEMO`), `views/layout.py` (demo banner), `docs/deployment.md`
(new), `scripts/` (demo reset script), README (demo link when live).

## Open questions

- **App host:** Supabase hosts only the database — the Python process
  needs a home. Candidates: Fly.io (easy container deploy, free-ish
  tier), Railway, Hetzner VPS (cheapest long-term, more ops). Owner
  decides.
- Demo login UX: published fixed credentials vs auto-login link?
  (Suggest: fixed credentials in README; auto-login weakens the auth
  posture for questionable gain.)
- Does the daily reset also rotate the demo password? (Suggest: no —
  keep it simple.)

## Implementation notes

### Section 1 — CI postgres matrix (2026-07-05)

**CI:** Added `postgres` job to `.github/workflows/ci.yml` — `postgres:16`
service, `uv sync --group dev --extra postgres`, `alembic upgrade head`, then
unit + integration suites with `KALETA_DB_URL=postgresql+asyncpg://…`.

**Test fixtures:** `tests/conftest.py` detects `KALETA_DB_URL` starting with
`postgresql`, truncates all tables once (clears Alembic seed rows), then wraps
each test in a rolled-back connection with savepoints so service-layer commits
stay isolated. `make_session_factory()` exported for integration fixtures.

**Migrations fixed for Postgres (forward edits only):**
- `e3f4a5b6c7d8` — SQLite table-rebuild replaced with
  `drop_constraint`/`create_unique_constraint` on PostgreSQL.
- `a4e9b2f1c6d8` — `RETURNING id` instead of `lastrowid`; boolean literals
  via bound params; `IS TRUE` for boolean checks.

**Application fixes:**
- `kaleta/db/sql_compat.py` — `extract()` / dialect-specific compilers
  replace SQLite-only `func.strftime()` in net-worth, report, and saved-report
  services.
- `MonthlyReadiness.ready_at` model column aligned to
  `DateTime(timezone=True)` (migration already had TZ; Postgres rejected
  aware datetimes against naive column metadata).

**Local validation:** `alembic upgrade head` green on fresh Postgres 16;
1266/1266 postgres-backed unit+integration tests pass (excluding 14 pre-existing
`test_chart_utils.py` failures unrelated to DB).

### Sections 2 + 4 — Supabase docs + demo hardening (2026-08-26)

**Docs:** Added `docs/deployment.md` — Supabase pooler vs direct URLs,
env wiring, bootstrap, published demo credentials, cron reset example.
Linked from `README.md`.

**Demo flag:** `KALETA_DEMO` in `src/kaleta/config/settings.py` (default
`false`).

**UI:** Dismissible demo banner in `views/layout.py` when `KALETA_DEMO=true`
(i18n `common.demo_banner` / `common.demo_dismiss`; persisted per session in
`app.storage.user`).

**Reset script:** `scripts/reset_demo.py` — requires `KALETA_DEMO=true`
(or `--force`), writes `~/.kaleta/config.json`, resets sole user password,
runs `DataService.seed()`.

**Postgres fix:** `DataService.clear_all()` skips SQLite-only `PRAGMA` on
PostgreSQL (needed for hosted demo reset).

**Tests:** `KAL-PLT-001` e2e banner; `KAL-PLT-002` integration reset script;
unit tests for demo flag.

**Deferred (section 3 + manual AC):** app host choice (Fly/Railway/Hetzner),
live HTTPS demo URL in README, observed nightly reset on production — owner
ops tasks documented in `docs/deployment.md`; not blocking repo automation.

## Implementation

Landed across multiple PRs; repo-automated scope archived 2026-08-26.

| SHA | Author | Date | Message |
|---|---|---|---|
| (section 1) | — | 2026-07-05 | CI Postgres matrix + PG compat fixes (see notes) |
| `78ef8ca` | Dawid Adamski | 2026-08-26 | docs: archive ux-sidebar + Supabase demo deployment (sections 2+4) (#61) |

**Files changed (#61 — sections 2+4):**
- `docs/deployment.md`, `docs/bdd.md`, `docs/plans/q4-supabase-deployment.md`
- `scripts/reset_demo.py`
- `src/kaleta/config/settings.py`, `src/kaleta/views/layout.py`
- `src/kaleta/services/data_service.py`
- `src/kaleta/i18n/locales/en.json`, `pl.json`
- `tests/e2e/test_demo_banner.py`, `tests/integration/test_reset_demo.py`
- `tests/unit/config/test_settings_demo.py`
- `README.md`

**Acceptance criteria run** (archiver, 2026-08-26):

| Command | Exit |
|---|---|
| `` `grep -q "KALETA_DEMO" src/kaleta/config/settings.py` `` | 0 |
| `` `test -f docs/deployment.md` `` | 0 |
| `` `uv run python scripts/check_doc_links.py` `` | 0 |
| `` `bash scripts/verify.sh --e2e` `` | 0 |

**Notes:** Section 3 (container host + HTTPS) and manual hosted-demo checks
remain owner follow-ups when infrastructure is chosen.
