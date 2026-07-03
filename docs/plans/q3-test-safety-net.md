---
plan_id: q3-test-safety-net
title: Test safety net — API integration + e2e for critical flows
area: testing
effort: large
status: draft
roadmap_ref: ../roadmap.md#q3-2026-jul-sep-stabilisation--debt
---

# Test safety net — API integration + e2e for critical flows

## Intent

The Q3 views refactor (`q3-views-refactor`) will move thousands of
lines. Services have unit coverage, but views and the REST API have
none — so regressions in the riskiest layer are currently invisible.
This plan builds the net **before** the refactor jumps.

## Scope

- API integration tests for every router in `src/kaleta/api/v1/`
  (accounts, categories, transactions, budgets, payees, institutions):
  happy path + validation error + not-found for each endpoint. ASGI
  test client (httpx), fresh in-memory SQLite per test via a session
  fixture, schema created from metadata (no Alembic in tests).
- Playwright e2e (extends existing `tests/e2e/` skeleton per ADR-021)
  for exactly 5 flows from `docs/bdd.md`:
  1. add / edit / split a transaction,
  2. CSV import (use `test_import.csv`) incl. account mapping,
  3. budget vs actual — create budget, add expense, verify bar,
  4. initial setup wizard end-to-end ("Finish Setup" gate),
  5. internal transfer detection between two accounts.
- A `make`/script entry (or documented commands) to run each suite.
- **Not in scope:** view unit tests, coverage targets, CI wiring
  (CI lands in `q3-engineering-hygiene`), any production code changes
  beyond minimal test hooks (e.g. exposing a test factory).

## Acceptance criteria

- `uv run pytest tests/integration/` green, covers all `api/v1` routes
  (assert via `--cov=src/kaleta/api` ≥ 90 % lines).
- `uv run pytest tests/e2e/` green; the suite launches its own ephemeral app
  on port 8081 (no manual server, no writes to the developer's `kaleta.db`).
  `docs/bdd.md` (reference the Gherkin headings in docstrings).
- Suites are independent: unit/integration need no running server.
- No flaky waits — e2e uses Playwright auto-waiting/locators, no
  `sleep`.

## Touchpoints

`tests/integration/` (new files per router), `tests/e2e/`,
`tests/conftest.py` (shared fixtures), possibly `src/kaleta/db/session.py`
(test session factory hook), `docs/bdd.md` (mark automated scenarios).

## Open questions

- Does the e2e suite seed via `scripts/seed.py` or a dedicated minimal
  fixture script? (Prefer dedicated — faster, deterministic.)
- Auth lands later in Q3 (`q3-auth-single-user`) — e2e login step will
  be added there; keep a single `login()` helper stub now.

## Implementation notes

- **E2e isolation (2026-07):** `tests/e2e/conftest.py` starts a subprocess Kaleta
  on port **8081** with ephemeral SQLite + isolated `HOME`. Alembic runs before
  startup. Override with `KALETA_E2E_BASE_URL` for debugging. Subprocess stdout is
  tee'd to a session log; the last 50 lines are attached to failed test reports.
- **Root cause of bulk e2e failures (2026-07):** Not Prophet blocking the async
  event loop — `ForecastService` already calls Prophet via
  `asyncio.run_in_executor`. Failures were:
  1. `seed_planned_transaction` called `asyncio.run()` from pytest-playwright's
     sync tests (running event loop) → `RuntimeError` / server 500s.
  2. Alembic migration seeds a root category named **Subscriptions**; the planned-
     transactions e2e test tried to create the same name → `IntegrityError` 500.
  3. When forecast e2e tests were included in a long suite run, heavy per-test
     seeding (90 API posts) plus multi-second Prophet CPU work on a single-worker
     server increased latency enough for unrelated seed HTTP calls to hit the
     default 10s client timeout — a capacity symptom, not missing `run_in_executor`.
  4. Full-suite UI failures on import/transfer verification: earlier tests seed
     hundreds of transactions; the transactions table is paginated, so rows from
     later tests were not on page 1. Fixed by filtering via the description search
     box instead of assuming first-page visibility.
- **Fixes applied:** `seed_planned_transaction` runs async HTTP in a worker thread;
  planned-transactions e2e uses a unique category name; import/transfer tests search
  by description. No seed client timeout increase.
- **Verification (2026-07-03):** `uv run pytest tests/e2e/ -q` — 43 passed twice in a
  row (~59s each); `kaleta.db` SHA-256 unchanged; slowest test 21.6s (forecast).
