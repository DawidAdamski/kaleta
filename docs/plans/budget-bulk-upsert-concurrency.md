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
Applying a yearly plan writes one monthly `Budget` row per
`(category, month, year)`. `BudgetService.bulk_upsert` (used by
`YearlyPlanService.apply`) did this as select-then-insert-or-update: it read the
year's existing rows, then INSERTed the ones it had not seen. Two applies of the
same brand-new plan that overlap both read no row for a key and both INSERT it,
so the second hits the unique constraint `uq_budget_category_period`
(`UniqueViolationError`). PR #344 removed the only UI trigger (a double Confirm
from stacked handlers), but the service itself still races if two applies ever
overlap. This makes the upsert atomic so the race cannot happen.

## Scope
- Replace the racy insert path in `BudgetService.bulk_upsert` with a single
  PostgreSQL `INSERT … ON CONFLICT (uq_budget_category_period) DO UPDATE`
  statement (`sqlalchemy.dialects.postgresql.insert(...).on_conflict_do_update`).
- Preserve all current behaviour for the non-concurrent case: duplicate input
  lines still sum, the return value is still the number of distinct keys written,
  empty input still returns 0, and on conflict the same columns are updated as
  the old ORM UPDATE path wrote.
- Not in scope: `YearlyPlanService.upsert` (the single `yearly_plans` row per
  year) — it has its own `uq_yearly_plans_year` and is a separate concern.
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
- `tests/integration/test_budget_bulk_upsert_concurrency.py` — new test (KAL-BBD-002).
- `docs/bdd.md` — KAL-BBD-002 under Feature: Budget Builder.

## Open questions
None.

## Implementation notes
- **Conflict target:** the named unique constraint `uq_budget_category_period`
  (`category_id, month, year`), passed as `constraint="uq_budget_category_period"`
  to `on_conflict_do_update` so the ON CONFLICT clause tracks the constraint
  definition in the `Budget` model rather than restating its columns.
- **Updated-column set on conflict:** `amount` and `updated_at`. The old ORM
  UPDATE set `row.amount` explicitly; marking the row dirty also fired the
  column's `onupdate=func.now()`, bumping `updated_at`. The ON CONFLICT `set_`
  reproduces exactly those two (`amount = excluded.amount`,
  `updated_at = func.now()`) and nothing else — `created_at`, `category_id`,
  `month`, `year`, `user_id` are left untouched, as before.
- **ON CONFLICT vs a lock:** chosen over a per-plan advisory/row lock because it
  is one statement the database serialises itself (no extra round-trip, no lock
  to acquire/release, no lock-ordering risk), and ADR-38 makes PostgreSQL the
  only database so there is no dialect branch to carry. A Core statement also
  carries the family's schema through `schema_translate_map`; raw `text()` SQL
  would not (AGENTS.md).
- **Test shape — deterministic, not merely idempotent:** the test drives a true
  overlap with two independent engines (two real Postgres connections) and
  `asyncio.gather`. Each `bulk_upsert` issues its work as its first await, so
  both transactions act on the empty state before either commits — the exact
  interleaving that triggers the bug. Verified: pre-fix it raises
  `IntegrityError (UniqueViolationError) … uq_budget_category_period`; post-fix
  both calls return 12 and exactly 12 rows exist, each 100.00. The test targets
  `bulk_upsert` directly rather than `YearlyPlanService.apply`, because `apply`
  also writes the single `yearly_plans` row whose `uq_yearly_plans_year` two
  concurrent applies would race on independently — out of this slice's scope.
- The two racing sessions commit for real (a race needs real commits), so the
  test creates its category and purges its `Budget` rows on both sides, leaving
  the shared suite schema as it found it.

## Implementation (filled by plan-archiver)
