---
plan_id: budgets-plan-unification
title: Budgets + Budget Plan — unify under a single Budgets page
area: budgets
effort: large
roadmap_ref: ../roadmap.md#budgets-current-budgets-view
status: in-progress
deferred_to: q4-2026
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

**Slice 1 was already on `main`** (commit 382a3f40, plan
`budgets-unification-slice-1`): the Plan tab on `/budgets`, the
`/budget-plan` shim, the sidebar entry removed, `budgets.tab_plan`, and
KAL-BUD-018. This branch delivers what that slice deferred.

- **Default tab is Realization** (open question 1, default taken).
  `?tab=` accepts `overview`, `realization` and `plan`, and anything else
  opens Realization (`tab_key_for` in `views/budgets/page.py`). On every
  tab switch the address is rewritten with `history.replaceState`, so a
  reload or a shared link comes back to the open tab. `replaceState` is used
  rather than `pushState` so that Back does not step through tab clicks.
- **The shim is now a real 302.** Slice 1 returned
  `RedirectResponse(...)` with the Starlette default of **307**, but the plan
  says 302. `budget_plan.plan_redirect()` sets `status_code=302`. A unit test
  checks the status and `location`, and the KAL-BUD-019 e2e test checks it on
  the wire (`max_redirects=0`). The route itself is still not removed: open
  question 4, default taken, removal goes in the follow-up PR.
- **Where the shared month selector lives** (open question 2): the page
  header strip, i.e. the tab row that artboard `2b` already uses for the
  Realization controls. It is not inside either panel. The month and year
  selects now show on both Realization and Plan, and both are bound to the
  same `realization_state`, so switching tabs resets nothing. The grouping
  toggle shows only on Realization. The Overview tab keeps its own date-range
  picker: it shows a range, not a month, and the plan's "both tabs" means
  Plan and Realization.
- **What "the month" means on the annual Plan grid.** The grid always shows
  twelve months, so the page's **year** becomes the planned year
  (`edit_year`), and the page's **month** becomes the copy-forward target.
  Copy-forward is clamped to February at the earliest, as before, because
  January has no earlier month in the same year to copy from. Earlier years
  that were already ticked stay as reference rows, and later ones are
  dropped, because the planned year is always the latest year shown, the
  same rule the year chips follow. Ticking a year chip on the Plan tab sends
  the new planned year back to the page (`on_edit_year_changed`), so the
  selector and Realization follow it. The plan panel is now a class,
  `PlanPanel` (`render`, `set_period`, `focus_category`), replacing the
  `render_plan_panel()` function.
- **Edit link** (open question 3, default **focus** taken): every
  Realization row has a small pencil beside the category name, with
  aria-label and tooltip `budgets.edit_category_link`. The plan said "when a
  category is over/under budget", and every row with a plan is one or the
  other, so the pencil is on every row. Clicking it switches to Plan and
  focuses that category's cell for the selected month. Each amount cell
  carries `data-plan-cell="<category_id>-<month>"` and `tabindex="-1"`: it
  can be focused from script, but there are no twelve extra tab stops per
  row. Pressing Enter on the focused cell opens the existing cell editor, so
  saving stays an explicit act. The focus script polls for up to about 3 s,
  because the tab has to become visible and a period change may be redrawing
  the grid. The pencil sits inside the category cell, so the six-column
  `2b` grid template is unchanged.
- **Keyboard: Alt+1 / Alt+2 / Alt+3.** The plan was written for two tabs,
  but slice 1 kept Overview as the first tab, and artboard `2b` draws
  Overview before Realization. Alt+digit therefore picks the tab in that
  position: Alt+1 Overview, Alt+2 Realization, Alt+3 Plan. The shortcut
  reads the physical key (`Digit1`…), not the character, because macOS types
  "¡" for Alt+1. `ui.keyboard` already ignores keys typed into inputs.
- **i18n:** `budgets.edit_category_link` was added to en and pl.
  `nav.budget_plan` never existed (slice 1 removed the entry without a key),
  so there is nothing to drop.
- **Tests:** `tests/unit/views/test_budgets_tabs.py` covers the shim (status
  and location), the sidebar no longer listing `/budget-plan`, the `?tab=`
  mapping and the Alt+digit mapping. `tests/e2e/test_budgets_unified.py`
  covers KAL-BUD-019..022. The existing Budget Plan e2e tests still start
  from `/budget-plan`, go through the redirect and pass unchanged, which
  satisfies "every current BDD scenario … still passes". `docs/bdd.md` now
  says above the feature that "the Budget Plan page" means the Plan tab.

