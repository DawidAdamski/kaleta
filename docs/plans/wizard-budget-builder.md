---
plan_id: wizard-budget-builder
title: Wizard — Budget Builder (yearly cadence)
area: wizard
effort: large
status: draft
roadmap_ref: ../product/financial-wizard.md#5-budget-builder
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

## Implementation notes

_(filled as work progresses)_
