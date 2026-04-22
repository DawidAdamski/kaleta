---
plan_id: wizard-budget-builder
title: Wizard — Budget Builder (yearly cadence)
area: wizard
effort: large
status: archived
archived_at: 2026-04-22
roadmap_ref: ../../product/financial-wizard.md#5-budget-builder
---

# Wizard — Budget Builder (yearly cadence)

## Intent

Budgeting works best when the user sets intent for the *year* and
then realises it monthly. The Budget Builder section walks the user
through a yearly intent pass, then derives a monthly plan, so each
month's allocation step (in Monthly Readiness) is a 1-minute confirm
instead of a 30-minute decision.

## Scope

- **Yearly intent**: a 4-step guided flow inside the wizard.
  1. Expected yearly income per source.
  2. Fixed costs (rent, utilities, subs, loans) — pre-filled from
     known planned transactions and subscriptions.
  3. Variable target envelopes — user sets yearly targets for groups
     like Food, Transport, Leisure.
  4. Reserve funds contributions — yearly target per fund (pulls
     from the Safety & Reserve Funds plan).
- **Derivation**: builder computes a default monthly allocation by
  even-split for variable envelopes, schedule-based for fixed costs,
  and equal contributions for funds.
- **Overrides**: user can bump a specific month (e.g. December
  Leisure +500) from a 12-cell grid; overrides don't affect other
  months.
- **Generation**: on "Apply" the builder writes `Budget` rows for
  all 12 months, respecting overrides; existing months are updated
  in-place rather than duplicated.
- **Re-run**: user can re-enter the builder mid-year; re-applying
  offers a diff of "what would change" before writing.

Out of scope:
- Multi-year forecasts — v1 is strictly 12 months ahead.
- Auto-suggestion of envelope targets from last year's actuals —
  next iteration.

## Acceptance criteria

- Completing the 4 steps for a fresh install generates 12 months of
  `Budget` rows whose variable-envelope totals sum to the declared
  yearly targets (±1 unit of rounding).
- Setting a December override raises only December's row.
- Re-running mid-year shows a diff list before committing changes.
- Fund contributions feed the matching `ReserveFund` rows
  proportionally.

## Touchpoints

- New model `YearlyPlan` — year, income_lines, fixed_lines,
  variable_lines, fund_lines (each a JSON blob or related tables).
- Alembic migration.
- `src/kaleta/services/yearly_plan_service.py` — derivation,
  diff computation, apply.
- `src/kaleta/services/budget_service.py` — bulk upsert by
  `(category_id, year, month)`.
- `src/kaleta/views/wizard.py` — builder flow.
- `src/kaleta/i18n/locales/*`.

## Open questions

- JSON blob vs relational child tables for the plan lines? Blob is
  quicker to ship; relational is nicer to query. v1: blob; revisit
  if reporting needs grow.
- Rounding strategy when yearly targets don't divide evenly — spread
  the remainder across the last 3 months of the year.
- Should the Budget Builder replace the current manual Budget create
  flow, or live alongside? v1: alongside — builder is a wizard
  entry point; manual per-month edits remain.

## Implementation

**Shipped 2026-04-22.**

| SHA | Author | Date | Message |
|---|---|---|---|
| `b0d9208` | Dawid | 2026-04-22 | feat(wizard): Budget Builder — yearly plan with apply + diff |

**Files changed:**
- `src/kaleta/models/yearly_plan.py` (new — single-row-per-year JSON blob per the v1 open-question answer)
- `src/kaleta/models/__init__.py` (export `YearlyPlan`)
- `alembic/versions/e6b2c1a9f083_add_yearly_plans.py` (new migration, SQLite + Postgres compatible)
- `src/kaleta/schemas/yearly_plan.py` (new: `IncomeLine`, `FixedLine`, `VariableLine`, `ReserveLine`, `YearlyPlanPayload`, `YearlyPlanResponse`, `BudgetDiff`, `BudgetDiffEntry`)
- `src/kaleta/services/yearly_plan_service.py` (new: `get`, `get_payload`, `upsert`, `derive`, `diff`, `apply`, `_split_yearly_to_months` — remainder spread over last 3 months)
- `src/kaleta/services/budget_service.py` (added `bulk_upsert(entries)` keyed on `(category_id, month, year)`)
- `src/kaleta/services/__init__.py` (export `YearlyPlanService`)
- `src/kaleta/views/budget_builder.py` (new `/wizard/budget-builder` page with Income / Fixed / Variable section cards, Apply flow with diff dialog)
- `src/kaleta/views/wizard.py` (replaces the Coming-soon badge on the Budget Builder step with an Open button linking to `/wizard/budget-builder`)
- `src/kaleta/main.py` (registers the new view)
- `src/kaleta/i18n/locales/en.json`, `src/kaleta/i18n/locales/pl.json` (new `budget_builder.*` block + `wizard.open` key)
- `tests/unit/services/test_yearly_plan_service.py` (23 tests, all passing: split invariants, derive scenarios, round-trip, apply idempotency, diff variants, bulk-upsert sum)

**What shipped:** Route `/wizard/budget-builder` loads or creates a `YearlyPlan` row for the current year. Users add Income / Fixed / Variable lines; variable and fixed-with-category lines contribute to a derived `(category_id, month) → amount` map using an even-split-with-remainder-to-last-3-months rule. Apply runs a diff against existing `Budget` rows and shows an approve dialog listing added + updated entries before writing. Re-entry during the year is safe — re-applying upserts by `(category_id, month, year)`, never duplicates.

**Partial coverage (flagged for follow-up):**
- **Reserve funds step** — placeholder card ("Reserves step coming soon") shown. Implementation deferred: depends on the Safety & Reserve Funds model, which the separate `wizard-safety-funds` plan owns. Schemas already accept `reserves_lines` for forward-compat.
- **Fixed-cost autofill from PlannedTransactions / subscriptions** — deferred. The `FixedLine` schema is ready; seeding from planned transactions is a separate follow-up.
- **12-cell month override grid** — deferred. v1 splits the yearly amount evenly (remainder on last 3 months). Per-month overrides will come after the reserve funds step lands, since both need the same grid UI.
- **Auto-suggestion of envelope targets from last year's actuals** — already out of scope per the plan.
