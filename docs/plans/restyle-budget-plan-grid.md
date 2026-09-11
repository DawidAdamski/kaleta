---
plan_id: restyle-budget-plan-grid
title: Restyle — Budget Plan grid on bare paper with actual sub-rows and a row context menu (artboard 2c)
area: budget-plan
effort: medium
status: draft
roadmap_ref: ../roadmap.md#budgets
---

# Restyle — Budget Plan grid: hairlines, actual sub-rows, context menu

## Intent

The annual grid in `views/budget_plan/grid.py` is the densest screen in
the app, so artboard `2c` gives it the opposite treatment from the rest:
**no card, no shadow** — hairlines only, and the paper is the table.
Each category becomes two rows: planned figures in ink, an `actual`
sub-row beneath in 10.5px mono muted, over-budget months in expense
colour. Empty future months render `—`, never `0`. The current month's
column is tinted; the recurring "Month" column stays, in accent. The
per-row `event_note` / `delete_sweep` buttons move into a right-click
context menu on the row to buy back the width the 12 month columns
need.

Depends on `restyle-theme-tokens`.

## Scope

- **Surface**: `_render_single_year_grid` renders on the page ground
  with `--k-hairline` row rules and `--k-border-strong` header rule; no
  `SECTION_CARD`. Horizontal scroll container (this grid does not
  reflow — handoff "Responsive behaviour").
- **Rows**: planned row (ink, `k-amount`), `actual` sub-row (10.5px
  `k-mono` muted; cell in `--k-expense` when actual > planned for that
  month). Actuals for the year come from the existing realization /
  budget-vs-actual service per month — one query per year, not per
  cell. Empty months `—`; current month column background `#F0E5D4`
  (dark: sunken surface); recurring "Month" column in accent text.
- **Context menu**: `ui.context_menu` on each category row with the two
  existing actions (`event_note` = edit notes / planned entries,
  `delete_sweep` = clear row), same handlers. Column header gains a
  small `more_horiz` hint icon with a tooltip "Right-click a row for
  actions" (discoverability; also the menu opens on the hint click for
  touch devices).
- **Compare grid** (`_render_compare_grid`): same hairline surface;
  no sub-rows (already shows two years).
- Toolbar (`toolbar.py`): controls in the title row, restyled only.
- BDD: `KAL-BUD-013` "budget plan row actions are reachable from the
  row context menu" (@automated, e2e `test_budget_plan.py`).

Out of scope: budget-plan data model, unification with budgets
(`budgets-plan-unification`, draft), comparisons logic, dialogs.

## Acceptance criteria

- `uv run pytest tests/e2e/test_budget_plan.py -q`
- `uv run pytest tests/unit/services/test_budget_service.py -q`
- `grep -q "context_menu" src/kaleta/views/budget_plan/grid.py`
- `grep -q "KAL-BUD-013" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`
- `bash scripts/verify.sh --e2e`
- `[manual]` Seed data, current year: no card around the grid; each
  category shows an `actual` sub-row; a month where actual > planned is
  terracotta; future months show `—`; the current month column is
  tinted; right-click on a row shows the two actions. Compare to
  artboard `2c` in light and dark.

## Touchpoints

- `src/kaleta/views/budget_plan/grid.py`, `toolbar.py`, `constants.py`,
  `helpers.py`
- `src/kaleta/services/budget_service.py` (yearly actuals per category
  — may already exist for comparisons; reuse)
- `src/kaleta/i18n/locales/en.json`, `pl.json`
  (`budget_plan.row_actions_hint`, `budget_plan.actual_row`)
- `docs/bdd.md`, `tests/e2e/test_budget_plan.py`

## Open questions

1. Keep the inline action buttons behind a "show actions" toggle for
   users who dislike context menus? Default: **no toggle** — the header
   hint icon opens the same menu, which covers touch.
2. Actual sub-row for income categories too? Default: **yes**, with
   under-plan (actual < planned) in expense colour for income rows,
   mirroring the realization semantics.

## Implementation notes

_Filled in as work progresses._
