---
plan_id: budgets-plan-comparisons-gaps
title: Budget planning comparisons — previous month across the year boundary, past years while editing
area: budgets
effort: medium
status: draft
roadmap_ref: ../roadmap.md#budgets
---

# Budget planning comparisons — previous month across the year boundary, past years while editing

Gap-closing plan for issue #6 (`KAL-CMP-001`, `KAL-CMP-002`), from
[`audit-planned-vs-code`](audit-planned-vs-code.md). `KAL-CMP-003` is
`@automated`.

## What exists (2026-09-23)

- `/budget-plan` single-year grid: a plan row and an "Actual" row per
  category for all twelve months — last month's actual sits beside the
  month being planned, *except* January (December is in last year's
  grid). The actual row hides when a category has neither plan nor
  actual. The only e2e (`test_budget_plan_page_shows_planned_and_actual_columns`)
  checks the "Actual" label, not a value.
- Year chips (today−4…today+1) show several years side by side — but
  compare mode is **read-only**, so you cannot plan July 2026 while
  looking at July 2024/2025.

## Scope

- **CMP-001** — January shows the previous December's actual; e2e
  asserts a seeded previous-month value in the row.
- **CMP-002** — editable current year with reference rows for chosen
  past years (actuals), instead of read-only compare mode.
- Coordinate with [`budgets-plan-unification`](budgets-plan-unification.md),
  which moves this grid under `/budgets?tab=plan`; whichever lands
  second rebases.

## Acceptance criteria

- `grep -qE "KAL-CMP-001 @automated" docs/bdd.md`
- `grep -qE "KAL-CMP-002 @automated" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`

## Open questions

- Past-year reference rows: actuals only, or plan too? Default: actuals
  only — the scenario asks for actuals and the grid is already dense.
