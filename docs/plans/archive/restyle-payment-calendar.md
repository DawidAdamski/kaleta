---
plan_id: restyle-payment-calendar
title: Restyle — Payment Calendar net-plus-dots day cells and a pinned overdue strip (artboard 3c)
area: payment-calendar
effort: medium
status: archived
archived_at: 2026-09-18
roadmap_ref: ../../roadmap.md#payment-calendar
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
  quick-add structure; restyle to tokens. ~~overdue items reachable
  there too (unchanged)~~ — **corrected during implementation**: this
  contradicted the bullet above it. The sheet only ever received the
  overdue list from the day-1 cell, so "day 1 no longer receives the
  overdue list" and "reachable in the sheet, unchanged" cannot both
  hold. The strip is the one place they live now; see Implementation
  notes.
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

- **Open question 1 — `Post both`: shipped `Post` only.** The default
  applies. `PlannedTransactionService._ensure_posted` creates exactly one
  `Transaction` per occurrence and there is no linked-counterpart or
  second-leg concept anywhere in the service, so no row could honestly
  offer `Post both`. The plan forbids adding posting logic here, so the
  `payment_calendar.post_both` key was not added either — a button that
  posts one leg while claiming two would be worse than the one we have.

- **Open question 2 — dot cap: 8, then `+N`.** Default taken.

- **A transfer's dot is flat, not red.** `grid_for_month` counts a
  transfer in neither `inflow` nor `outflow`, so it contributes nothing
  to the day's net. Giving it the expense colour would have the dots
  claim a direction the figure beside them does not have. Projected
  subscription charges are flat too, for a different reason: they are
  the only items in a cell that cannot be posted. Both are unit-tested.

- **The cell's figure is the day's net, and it hides at zero.** Two items
  that cancel out still draw their dots, so an empty day and a balanced
  day do not look alike — `DayMarks.is_empty` is about the dots, not the
  figure.

- **Selecting a day toggles two classes; it does not redraw the grid.**
  The click handler lives on a cell inside `grid_container`, and clearing
  that container from inside the handler deletes the slot the handler
  belongs to — NiceGUI raises on it. `_select_day` removes the warm class
  from the previously selected cell and adds it to the new one, which is
  also cheaper than rebuilding thirty-one cells.

- **Three reading levels for the day number, no weekend tint.** Today in
  ink, a working day in `--k-muted-strong` (`CALENDAR_DAY_NUM`), a
  weekend in plain muted. Tinting whole weekend columns would stripe the
  grid and compete with the selected day's warm surface for the same
  signal.

- **`payment_calendar.overdue_title` retitled to plain "Overdue".** It
  read "Overdue (last 30 days)" while the window is configurable
  (`payment_calendar_overdue_days`). Buried in the day sheet a stale 30
  was survivable; pinned above the grid it would be a wrong number on
  every page load for anyone who changed the setting. Each row carries
  its own age, so the heading does not need the window at all. The
  setting itself is untouched, as the plan requires.

- **The day sheet no longer lists overdue items, and the Scope bullet
  saying it would has been struck through.** Two Scope bullets
  contradicted each other: "Day 1 no longer receives the overdue list"
  and "overdue items reachable there too (unchanged)". The day-1 cell
  was the *only* route by which `_open_day` ever received them, so
  removing the first removes the second. They live in the strip now,
  which is visible without opening any day and from any month — the
  point of the change. The sheet keeps totals, planned items,
  subscription charges and quick-add.

- **The strip shows what is late *today*, not what the browsed month
  says.** `grid_for_month` windows its overdue bucket against the month
  on screen — the thirty days before its first. Page forward one month
  with the existing arrows and that window lands in the future, and an
  age computed from it reads "-5 days late". The day-1 cell never
  printed an age, so this was harmless until the strip started showing
  one. `actually_overdue()` filters to `date < today` and sorts oldest
  first; the overdue KPI takes the same filter, so the count and the
  strip cannot disagree. Unit-tested.

- **One amount rule for both rows.** `occurrence_amount()` gives the
  figure and its tone, and the strip and the day sheet both read it. The
  sheet's row had been treating every non-income occurrence as an
  expense, so a planned transfer showed in red with a minus sign while
  the same item's dot in the day cell was already flat. Money between
  the user's own accounts did not leave. Fixed in place rather than
  filed, per the chore rule for a one-liner in a file the branch already
  owns.

- **Stacking:** branched from `plan/restyle-net-worth`, which is itself
  unmerged. Open the PR with `--base plan/restyle-net-worth`; it must
  merge after every branch below it.

## Implementation

Landed on 2026-09-18.

| SHA | Author | Date | Message |
|---|---|---|---|
| `d3fa976` | Dawid (Ani) | 2026-09-15 | feat(payment-calendar): a day is a net and a row of dots |

**Files changed:**
- docs/bdd.md
- docs/plans/restyle-payment-calendar.md
- src/kaleta/i18n/locales/en.json
- src/kaleta/i18n/locales/pl.json
- src/kaleta/views/payment_calendar.py
- src/kaleta/views/theme.py
- tests/e2e/test_planned_transactions.py
- tests/unit/views/test_payment_calendar_cells.py

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| _(skipped: --fast, validated by PR CI)_ | – |
