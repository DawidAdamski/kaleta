---
plan_id: budgets-plan-unification
title: Budgets + Budget Plan — unify under a single Budgets page
area: budgets
effort: large
roadmap_ref: ../roadmap.md#budgets-current-budgets-view
status: draft
---

# Budgets + Budget Plan — unify under a single Budgets page

## Intent

Today Kaleta has **two** budget-related destinations:

- `/budgets` — realization view (how is the month going, donut +
  variance summary).
- `/budget-plan` — table-based planning editor (rows per category,
  monthly amounts, copy-from-previous).

Users don't think about budgets as two pages — they think about one
thing with two modes (plan the month, then track the month). The
split forces context switching and double navigation whenever they
adjust a planned amount after seeing realization.

Merge both into a single `/budgets` destination with two tabs:
**Plan** (the table editor from Budget Plan) and **Realization**
(the current Budgets view). Keep both as first-class — neither
loses functionality.

## Scope

- **Route consolidation** — `/budgets` becomes the canonical page.
  `/budget-plan` 302-redirects to `/budgets?tab=plan` for one
  release, then the route is removed in a follow-up.
- **Tabs** — `ui.tabs` with two panels:
  - `Plan` — the existing Budget Plan table (all its features:
    month selector, row per category, copy-previous-month,
    multi-row paste, subtotals).
  - `Realization` — the existing Budgets realization view (donut
    per category, variance chips, month range selector).
- **Shared month selector** at the page level — both tabs respect
  the same "which month" choice so switching tabs doesn't reset
  context.
- **Edit affordance from Realization** — when a category on the
  Realization tab is over/under budget, a small edit icon jumps to
  the Plan tab with that category's row focused.
- **URL state** — `?tab=plan` or `?tab=realization`; default is
  `realization` (matches the user's complaint that the today's
  Budgets view is where they go most often).
- **Layout nav** — "Budget Plan" entry is removed from the
  sidebar; only "Budgets" remains.
- **Keyboard** — `Alt+1` / `Alt+2` switches tabs on the unified
  page.
- **i18n** — `budgets.tab_plan`, `budgets.tab_realization`,
  `budgets.edit_category_link`, plus nav/sidebar label updates.
- **Tests** — unit-test the redirect shim; smoke-test both tabs
  load under `/budgets`.

Out of scope:
- Changing the editor's model (still row-per-category-per-month).
- Multi-month range editing in the Plan tab.
- A third tab for Forecast (Forecast stays at `/forecast`).
- Mobile layout overhaul — tabs collapse but widget rearrangement
  is separate.

## Acceptance criteria

- Navigating to `/budgets` renders the page with the Realization
  tab active by default.
- Clicking the `Plan` tab (or visiting `/budgets?tab=plan`) shows
  the full Budget Plan table editor with all current features
  intact.
- Changing the month in the header selector updates both tabs.
- Clicking the edit pencil on a category in Realization switches
  to Plan with that category's amount field focused.
- `/budget-plan` still works for one release (302 to
  `/budgets?tab=plan`); sidebar no longer links to it.
- Every current BDD scenario for Budgets and Budget Plan still
  passes (migrated or moved under the unified page).

## Touchpoints

- `src/kaleta/views/budgets.py` — becomes the unified page; pulls
  in the Plan panel as a component.
- `src/kaleta/views/budget_plan.py` — refactor its page body
  into a reusable `render_plan_panel(session, month)` function;
  keep the module for the redirect shim.
- `src/kaleta/views/layout.py` — remove the Budget Plan nav entry.
- `src/kaleta/main.py` — no route removal (the shim still
  registers `/budget-plan` for the grace period).
- `src/kaleta/i18n/locales/{en,pl}.json` — new tab labels, drop
  `nav.budget_plan` after grace period.
- `docs/bdd.md` — consolidate scenarios under "Budgets".
- `tests/e2e/` — update Playwright selectors if they targeted
  `/budget-plan`.

## Open questions

1. **Default tab** — Realization or Plan? Default: **Realization**
   (matches the roadmap note "Budgets is where the user *checks*").
2. **Should the shared month selector live in the tab body or the
   page header?** Default: **page header**, so it persists when
   switching tabs without re-fetching.
3. **Edit-link target** — focus the category amount field, or open
   the inline edit popover directly? Default: **focus** — leaves
   the user's save action explicit.
4. **When to remove the `/budget-plan` redirect?** Default: **in
   the PR following this one's merge**, so we get one release cycle
   of grace.

## Implementation notes
_Filled in as work progresses._
