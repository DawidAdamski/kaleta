---
plan_id: restyle-budget-plan-grid
title: Restyle — Budget Plan grid on bare paper with actual sub-rows and a row context menu (artboard 2c)
area: budget-plan
effort: medium
status: in-progress
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
- BDD: `KAL-BUD-015` "budget plan row actions are reachable from the
  row context menu" and `KAL-BUD-016` "the plan grid marks the month I am
  in" (@automated, e2e `test_budget_plan.py`). Renumbered from the plan's
  original `KAL-BUD-013`, which was taken — see Implementation notes.

Out of scope: budget-plan data model, unification with budgets
(`budgets-plan-unification`, draft), comparisons logic, dialogs.

## Acceptance criteria

- `uv run pytest tests/e2e/test_budget_plan.py -q`
- `uv run pytest tests/unit/services/test_budget_service.py -q`
- `grep -q "context_menu" src/kaleta/views/budget_plan/grid.py`
- `grep -q "KAL-BUD-015" docs/bdd.md`
- `grep -q "KAL-BUD-016" docs/bdd.md`
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

### Read this before reviewing the diff

Fourth in a stack: `plan/restyle-theme-tokens` → `plan/restyle-dashboard` →
`plan/restyle-transactions-filter-chips` → `plan/restyle-budgets-pace-bars`
→ this one. None merged yet. This plan's own diff is:

    git diff plan/restyle-budgets-pace-bars...HEAD

and its PR is opened with `--base plan/restyle-budgets-pace-bars`.

### Open questions — decisions taken

1. **No "show actions" toggle.** The actions are on the row's own
   `more_horiz` button as well as its right-click menu, so a user who never
   right-clicks a table row loses nothing and a touch screen works. A toggle
   would be a preference for a thing that has two ways in already.
2. **The question about income rows does not arise.** `load_annual_plan_grid`
   builds its rows from `CategoryService.list(type=CategoryType.EXPENSE)` —
   the plan grid has never shown income categories, so there are no income
   sub-rows to decide the colour of. Left untouched; bringing income into the
   grid is `budgets-plan-unification` territory.

### The scenario ID in the plan was already taken

Scope asks for `KAL-BUD-013`. That ID went to the pace-bar scenario in
`restyle-budgets-pace-bars`, one branch down this stack, which was written
first. The context-menu scenario is **KAL-BUD-015**, and **KAL-BUD-016**
covers the tinted current-month column — new user-facing behaviour that
Working Agreement §5 wants a scenario for, and the thing the `[manual]`
criterion looks at first.

### Two buttons became a menu, and a button

The per-row `event_note` / `delete_sweep` pair cost 76px of a grid whose
twelve month columns are squeezed to 52px each. Both actions moved into one
`ui.context_menu` on the row — and into one `more_horiz` button, because a
touch screen has no right mouse button and nobody discovers a context menu
on a table row by accident. The header's actions column carries the same
`more_horiz` glyph with "Right-click a row for actions" as its tooltip.

The handlers are the same two calls as before; only the way in changed.

### The header hint is a hint, not a control

Scope says the header's `more_horiz` "opens the menu on the hint click for
touch devices". A header icon cannot open a *row's* menu — it does not know
which row — so it carries the tooltip only, and touch is served by the
`more_horiz` button on each row. The header glyph is there to say the
actions column still exists and where its contents went.

### The actual sub-row stopped painting every month green

`actual_cell_color` returned green for any month with spending and red for
an overspend. A year of ordinary months came out as a wall of green saying
only "you spent money", which is what a ledger always says. The sub-row is
muted mono now, and **only** an overspent month takes a colour —
artboard 2c's reading, and the same rule the pace bars use one branch down.

KAL-BUD-006 said so in as many words — "under-budget categories are
highlighted in green" — so the scenario changed with the code, not around
it. It now reads "a month that stayed inside its budget is not [highlighted]
— spending as planned is not news", and its e2e asserts the absence of the
expense colour rather than the presence of green.

### The dark tint is not the sunken surface

Scope names the sunken surface for the dark current-month column. In dark
mode `--k-surface-sunken` and `--k-hairline` are the same colour
(`#2A2822`), so the tinted cell would have painted over the row's own rule
and left a 52px gap in every hairline, once per row, straight down the
middle of the grid. `--k-plan-now` is `#332F26` in dark instead: a step
above the hairline, still clearly a tint against the `#201F1A` ground.

### Both lines of a category are mono

Scope asks for the planned row "in ink, `k-amount`". It reads `k-ink` and
`k-mono` rather than `k-amount`: `k-amount` is `k-mono` plus a semantic
colour, and the plan figures have their own colour rule already (ink,
accent when a month overrides the recurring figure, muted when empty). What
mattered was the mono half — the actual line under each plan was mono and
the plan line was not, so the two rows of one category used different
typefaces and their digits did not line up column by column.

### A category is one row, not two

The plan line and its actual line used to be two independent rows, each with
its own hairline and its own hover. Artboard 2c reads the pair as one
category, so they sit inside one wrapper that carries the hairline, the
hover and the right-click menu; the lines themselves carry neither.

### The compare grid's category heading is a hairline

It was a slate band; the first pass made it `PLAN_HEAD` + `k-eyebrow`, which
put a strong rule under every category and uppercased user-entered names —
"ŻYWNOŚĆ" with 0.2em of letter-spacing. The theme's own comment says the
header and the totals band are the only strong rules, so the heading is a
hairline row with the name in ink, spelled the way the user spelled it.

### The compare grid kept its actual sub-rows

Scope says the compare grid has "no sub-rows (already shows two years)".
That reads two ways: *remove* the actual rows it already had, or *do not
add* the new-style ones. They were removed first, and put back — deleting
a year's spending from the only screen that shows it beside another year's
is a data change, not a restyle, and it is not a call to make from an
ambiguous clause. The rows are there, restyled to the same quiet rule as the
single-year grid, and paired with their plan line the same way.

If the owner wants them gone, that is a one-line deletion and a scenario
step; it should not be the default reading of a sentence.

### `is_dark` stopped deciding anything

The grid picked four class strings off `app.storage.user["dark_mode"]`
(`bg-slate-600` vs `bg-slate-100`, and so on). Every one of them is now a
token that answers `.body--dark` on its own, so the flag, the branches and
the `app` import are gone. The tinted column is a token like every
other colour in the stylesheet — `--k-plan-now`, `#F0E5D4` from the artboard
in the light block and `#332F26` in the dark one (see "The dark tint is not
the sunken surface" above).

### Not done

The `[manual]` criterion — the whole grid compared to artboard 2c in light
and dark, with a real year of data — is the owner's visual pass, and it is
where the compare-grid question above gets settled. The toolbar was left
alone beyond what the page ground gives it; Scope calls it "restyled only",
and it already reads as the artboard does.
