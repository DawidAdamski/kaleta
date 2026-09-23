---
plan_id: funds-reserve-derived-target
title: Reserve funds — target derived from 12-month average spending
area: budgets
effort: small
status: draft
roadmap_ref: ../roadmap.md#budgets
---

# Reserve funds — target derived from 12-month average spending

Gap-closing plan for issue #13 (`KAL-FND-002`), from
[`audit-planned-vs-code`](archive/audit-planned-vs-code.md). `KAL-FND-001` and
`KAL-FND-003` are `@automated`; this is the last gap.

## Intent

"A 3-month reserve" should mean three months of *what I actually
spend*, not a number typed into the dialog.

## What exists (2026-09-23)

- `ReserveFund.emergency_multiplier` and the multiplier input
  (`views/safety_funds.py`) — it only draws tick marks on a manual
  target.
- `ReserveFundService.trailing_monthly_expense` averages **90 days** and
  feeds "months of coverage"; the what-if simulator shares it.

## Scope

- `ReserveFundService.derived_target(fund)` = multiplier × average
  monthly expense over the last 12 months (non-transfer expenses);
  the dialog offers "derive from spending" vs a manual target.
- Keep one averaging function with a window parameter; do not fork the
  formula the what-if simulator depends on.

## Acceptance criteria

- `grep -qE "KAL-FND-002 @automated" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`

## Open questions

- Should months of coverage also move to 12 months? Default: no — keep
  90 days there, the target uses 12; record both in the dialog's hint.
