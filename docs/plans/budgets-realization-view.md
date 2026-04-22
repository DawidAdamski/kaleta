---
plan_id: budgets-realization-view
title: Budgets — realization view (plan vs actual)
area: budgets
effort: medium
status: draft
roadmap_ref: ../roadmap.md#budgets
---

# Budgets — realization view (plan vs actual)

## Intent

The current Budgets page shows allocations but not how they are being
burned down over the month. Add a focused "realization" view that
answers "for each category: how much did I plan, how much did I spend,
how much is left, and am I on pace?"

## Scope

- New `Realization` tab on Budgets, defaulting to current month.
- Row per budgeted category: Planned, Actual, Remaining, % of period
  elapsed, % of budget used, status chip (on-track / warning / over).
- Sorting: worst-performing first by default.
- Group switch: by Category / by Group / Flat.

Out of scope:
- Forecasting end-of-month burn (already covered by Forecast module).
- Editing budgets from this view — read-only; edits happen on the
  Planning tab.

## Acceptance criteria

- Current-month totals reconcile to the per-category rows within
  0.01.
- Status chip logic:
  - on-track: `used_pct <= elapsed_pct + 5`
  - warning: `elapsed_pct + 5 < used_pct <= 100`
  - over: `used_pct > 100`
- Switching months via the existing month picker refreshes all rows.
- Empty state (no budgets): friendly CTA to "Create a budget".

## Touchpoints

- `src/kaleta/views/budgets.py` — add the tab.
- `src/kaleta/services/budget_service.py` — `realization_for_month`
  returning the per-category breakdown.
- `src/kaleta/schemas/budget.py` — response schema for the view.
- `src/kaleta/i18n/locales/*`.

## Open questions

- Warning threshold — fixed 5% or user-configurable? v1: fixed.
- Status colour for "warning" — reuse the existing `amber-7` token
  from the theme; confirm once rendered.

## Implementation notes

_(filled as work progresses)_
