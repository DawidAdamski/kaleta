---
plan_id: budgets-annual-review
title: Annual review — guided year close on top of the yearly plan tooling
area: budgets
effort: large
status: draft
roadmap_ref: ../roadmap.md#budgets
---

# Annual review — guided year close on top of the yearly plan tooling

Gap-closing plan for issue #9 (`KAL-ANR-001`…`003`), from
[`audit-planned-vs-code`](audit-planned-vs-code.md).

## What exists (2026-09-23)

- No Annual Review page, route or wizard step.
- Building blocks: per-category yearly plan-vs-actual totals on
  `/budget-plan` (`PlanCategoryRow.total_planned/total_actual`);
  `YearlyPlanService` (payload, derive, diff, apply) works for any year,
  but `/wizard/budget-builder` is locked to the current year;
  `copy_forward` is month-to-month only.
- Subscriptions exist; irregular-fund items do not (see
  [`funds-irregular-items`](funds-irregular-items.md)).

## Scope

- **ANR-001** — review page, step 1: plan vs actual per category for the
  year (reuse the grid's totals).
- **ANR-002** — step 2: carry the year into next year with per-category
  % adjustments, applied through `YearlyPlanService.diff/apply` for
  `year + 1`.
- **ANR-003** — step 3: keep / adjust / drop for each subscription and
  irregular item. Depends on `funds-irregular-items` for the items;
  ship subscriptions first if that plan has not landed.

## Acceptance criteria

- `grep -cE "KAL-ANR-00[1-3] @automated" docs/bdd.md | grep -q '^3$'`
- `uv run python scripts/spec_coverage.py`

## Open questions

- New page or a mode of the budget builder? Default: a mode of the
  budget builder with a year selector — it already owns
  payload/diff/apply.
