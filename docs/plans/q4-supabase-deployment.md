---
plan_id: q4-supabase-deployment
title: Hosted instance on Supabase Postgres + CI postgres matrix
area: infrastructure
effort: large
status: draft
roadmap_ref: ../roadmap.md#q4-2026-open-source-launch
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

**Not touched (other plan sections):** Supabase docs, demo flag, hosting, demo
reset, UI banner.
