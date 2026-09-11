---
plan_id: restyle-payment-calendar
title: Restyle — Payment Calendar net-plus-dots day cells and a pinned overdue strip (artboard 3c)
area: payment-calendar
effort: medium
status: draft
roadmap_ref: ../roadmap.md#payment-calendar
---

# Restyle — Payment Calendar: net + dots per day, pinned overdue strip

## Intent

`_draw_day_cell` in `views/payment_calendar.py` stacks an inflow line,
an outflow line and a count badge in every cell — 31 cells × 3 numbers.
Artboard `3c` shows **the day's net plus a row of small dots**, one per
item, coloured by direction; totals live in the month KPI row and in
the day sheet where there is room. Overdue items move out of the day-1
cell into a **pinned strip** above the grid listing each overdue item
with its age and a `Post both` action. Today's cell gets a 2px ink
border and a `Today` label; the selected day gets the warm surface.

Depends on `restyle-theme-tokens`.

## Scope

- **Day cell**: day number (`k-mono`, muted; today in ink with a
  `Today` label), net for the day (`k-amount`, signed, hidden when
  zero), then a dot row — one 6px dot per occurrence (income / expense
  colour; subscription charges in neutral bar colour), capped at 8 with
  a `+N` tail. Today: 2px `--k-ink` border. Selected: `--k-surface-warm`
  background. Weekend columns: muted day numbers only.
- **Overdue strip**: above the grid, `--k-surface-warm` with a
  `--k-warning` left rule, one row per overdue occurrence: name, amount,
  `N days` age, and actions — `Post` (existing post-occurrence handler)
  and `Post both` when the occurrence is a transfer pair / has a linked
  counterpart (reuse the existing "post both sides" logic if present;
  otherwise `Post` only — see open question). Day 1 no longer receives
  the overdue list.
- **Day sheet** (`_open_day`): keeps totals / planned / subscription /
  quick-add structure; restyle to tokens; overdue items reachable there
  too (unchanged).
- **KPI row**: month in / out / net / overdue count — already exists;
  restyle with mono figures.
- `payment_calendar_overdue_days` storage key unchanged.
- BDD: `KAL-PLN-020` "overdue occurrences are listed in a strip above
  the calendar" (@automated, e2e `test_planned_transactions.py`).

Out of scope: planned-transaction model, posting semantics, the
lookback setting, subscriptions.

## Acceptance criteria

- `uv run pytest tests/e2e/test_planned_transactions.py -q`
- `uv run pytest tests/unit/services/test_planned_transaction_service.py -q`
- `grep -q "KAL-PLN-020" docs/bdd.md`
- `grep -q "overdue_strip" src/kaleta/views/payment_calendar.py`
- `uv run python scripts/spec_coverage.py`
- `bash scripts/verify.sh --e2e`
- `[manual]` Seed data with an overdue occurrence: strip above the grid
  shows it with its age and Post; day cells show net + dots only; today
  has an ink border and label; clicking a day tints it warm and opens
  the sheet with totals. Compare to artboard `3c` in light and dark.

## Touchpoints

- `src/kaleta/views/payment_calendar.py` (`_draw_day_cell`, grid,
  new `_overdue_strip`, `_open_day`)
- `src/kaleta/services/planned_transaction_service.py` (read-only;
  `PlannedOccurrence` may need an `is_income` / `kind` accessor if not
  present)
- `src/kaleta/i18n/locales/en.json`, `pl.json`
  (`payment_calendar.today`, `payment_calendar.overdue_age`,
  `payment_calendar.post_both`, `payment_calendar.more_items`)
- `docs/bdd.md`, `tests/e2e/test_planned_transactions.py`

## Open questions

1. `Post both` semantics — does a transfer-type planned occurrence post
   two transactions today? Default: **if the service already posts both
   legs for transfers, label the button `Post both` for those rows;
   otherwise ship `Post` only** and record it in Implementation notes.
   Do not add new posting logic in this plan.
2. Dot cap per cell? Default: **8 dots then `+N`**.

## Implementation notes

_Filled in as work progresses._
