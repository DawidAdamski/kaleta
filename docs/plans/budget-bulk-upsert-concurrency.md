---
plan_id: budget-bulk-upsert-concurrency
title: Budget bulk-upsert is concurrency-idempotent for a brand-new plan
area: budgets
effort: small
status: in-progress
roadmap_ref: ../roadmap.md#q3-2026-jul-sep-stabilisation--debt
---

# Budget bulk-upsert is concurrency-idempotent for a brand-new plan

## Intent
Applying a yearly plan (`YearlyPlanService.apply`) writes the single
`yearly_plans` row for the year and then one monthly `Budget` row per
`(category, month, year)`. Both writes used select-then-insert-or-update: read
the current row(s), then INSERT what was not seen. Two applies of the same
brand-new plan that overlap race on *both* writes — first on `uq_yearly_plans_year`
(both read no plan row and both INSERT it), then, had they got past it, on
`uq_budget_category_period` for the budget rows. Either surfaces as
`UniqueViolationError`. PR #344 removed the only UI trigger (a double Confirm from
stacked handlers), but the services themselves still raced whenever two applies
overlapped. This makes both upserts atomic so the real Budget Builder apply path
is concurrency-idempotent end to end.

## Scope
- Replace the racy insert path in `BudgetService.bulk_upsert` with a single
  PostgreSQL `INSERT … ON CONFLICT (uq_budget_category_period) DO UPDATE`
  statement (`sqlalchemy.dialects.postgresql.insert(...).on_conflict_do_update`).
- Replace the racy select-then-insert-or-update in `YearlyPlanService.upsert`
  with the same pattern, targeting `uq_yearly_plans_year`, so the whole
  `apply()` path (yearly_plans row + budget rows) is idempotent.
- Preserve all current behaviour for the non-concurrent case: for `bulk_upsert`,
  duplicate input lines still sum, the return value is still the number of
  distinct keys written, empty input still returns 0; for `upsert`, the written
  row is still returned. On conflict each writes exactly the columns the old ORM
  UPDATE path wrote.
- Emit the budget rows in a stable key order so two overlapping multi-row upserts
  cannot deadlock on their row locks.
- Not in scope: any view change; this is a service-layer fix.

## Acceptance criteria
- `uv run pytest tests/integration/test_budget_bulk_upsert_concurrency.py -q`
- `uv run pytest tests/integration/test_budgets.py tests/integration/test_annual_review.py tests/unit/services/test_yearly_plan_service.py -q`
- `grep -q "KAL-BBD-002" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`
- `uv run mypy src/`
- `uv run lint-imports`

## Touchpoints
- `src/kaleta/services/budget_service.py` — `bulk_upsert`.
- `src/kaleta/services/yearly_plan_service.py` — `upsert`.
- `tests/integration/test_budget_bulk_upsert_concurrency.py` — new test (KAL-BBD-002).
- `docs/bdd.md` — KAL-BBD-002 under Feature: Budget Builder.

## Open questions
None.

## Implementation notes
- **Conflict targets (named constraints):**
  - `bulk_upsert`: `uq_budget_category_period` (`category_id, month, year`).
  - `upsert`: `uq_yearly_plans_year` (`year`).
  Both passed as `constraint=<name>` to `on_conflict_do_update`, so the ON
  CONFLICT clause tracks the model's constraint definition rather than restating
  its columns.
- **Updated-column set on conflict (exactly what the old ORM UPDATE wrote):**
  - `bulk_upsert`: `amount` and `updated_at`. The old UPDATE set `row.amount`
    explicitly; marking the row dirty also fired `updated_at`'s
    `onupdate=func.now()`. The `set_` reproduces those two
    (`amount = excluded.amount`, `updated_at = func.now()`) and nothing else —
    `created_at`, `category_id`, `month`, `year`, `user_id` untouched.
  - `upsert`: the four line columns (`income_lines`, `fixed_lines`,
    `variable_lines`, `reserves_lines`) `= excluded.<col>`, plus
    `updated_at = func.now()` (same `onupdate` effect). `year` / `created_at`
    untouched. The four columns are `EncryptedText`; `excluded.<col>` is the
    already-encrypted value proposed for insertion, so the ciphertext written on
    update is identical to the insert path. `upsert` keeps its `-> YearlyPlan`
    contract via `RETURNING` the ORM entity (`scalar_one()`), so no second
    round-trip is needed.
- **ON CONFLICT vs a lock:** chosen over a per-plan advisory/row lock because it
  is one statement the database serialises itself (no extra round-trip, no lock
  to acquire/release, no lock-ordering risk), and ADR-38 makes PostgreSQL the
  only database so there is no dialect branch to carry. Core statements also
  carry the family's schema through `schema_translate_map`; raw `text()` SQL
  would not (AGENTS.md).
- **Deterministic insert order / deadlock:** `bulk_upsert` emits rows in sorted
  `(category_id, month, year)` order so two overlapping multi-row upserts take
  their row locks in the same order and cannot deadlock.
- **asyncpg bind-param cap:** `bulk_upsert` sends four params per row, so the
  32767-parameter cap allows ~8000 rows (~680 categories × 12 months). A plan
  never approaches that, so no chunking was added (noted in the code).
- **Test shape — deterministic, at the apply level the scenario promises:** the
  test drives a true overlap with two independent engines (two real Postgres
  connections) and `asyncio.gather`, aligned on an `asyncio.Barrier` (`_race`).
  A single-row `yearly_plans` INSERT+COMMIT is fast enough that, left to chance
  under single-thread asyncio, the first racer commits before the second reads —
  the race never shows (verified: plain two-way gather passed pre-fix). The
  barrier releases both only once both connections are open and both have reached
  the call, so both issue their read against the empty table before either
  commits — the overlap a second web worker creates. Two cases, both covering
  KAL-BBD-002: the `bulk_upsert`-direct budget race, and the end-to-end
  `YearlyPlanService.apply` race (the real Budget Builder path). Verified
  pre-fix: the apply case raises
  `UniqueViolationError … uq_yearly_plans_year` (reliably, 4/4); the
  `bulk_upsert` case raised `… uq_budget_category_period` before its fix.
  Verified post-fix: both pass reliably (5/5) — neither raises, exactly one
  `yearly_plans` row and twelve budget rows each 100.00. Post-fix under READ
  COMMITTED the ON CONFLICT writes serialise through the row lock with no
  serialization failure to retry.
- The racing sessions commit for real (a race needs real commits), so the test
  fixture creates its category and purges its `Budget` / `yearly_plans` rows on
  both sides, leaving the shared suite schema as it found it. `category_id` is
  initialised to `None` before the setup `try`, so the `finally` cleanup never
  raises `UnboundLocalError` if setup fails and the engines are always disposed.

## Implementation (filled by plan-archiver)
