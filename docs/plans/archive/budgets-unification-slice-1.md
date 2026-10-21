---
plan_id: budgets-unification-slice-1
title: Budgets unification — slice 1 (Plan tab + /budget-plan redirect)
area: views (budgets)
effort: small
status: archived
archived_at: 2026-10-21
roadmap_ref: ../../roadmap.md#budgets-current-budgets-view
---

# Budgets unification — slice 1 (Plan tab + /budget-plan redirect)

## Intent

First self-contained increment of the large
[`budgets-plan-unification`](../budgets-plan-unification.md) draft. That draft
wants the two budget destinations merged into one `/budgets` page with tabs so
the user plans and tracks the month in one place instead of context-switching
between `/budgets` and `/budget-plan`.

`/budgets` today already carries a two-tab strip — **Overview** and
**Realization** (`views/budgets/page.py:197-198`). The planning grid editor
still lives on its own route `/budget-plan` (`views/budget_plan/`, its own nav
entry). This slice brings the planning editor onto `/budgets` as a third
**Plan** tab, makes `/budget-plan` a 302 redirect onto it, and drops the
separate sidebar entry — the user-visible half of the unification. The deeper
cross-tab integration (shared month selector, edit-pencil jump, removing the
grace-period route) is deferred to slice 2+.

## Scope

- **`src/kaleta/views/budget_plan/panel.py`** (new) — extract the body of
  `budget_plan_page()` (dialogs + toolbar + grid, everything *inside*
  `page_layout`) into a reusable `render_plan_panel()` coroutine. The grid and
  toolbar components are unchanged; only their host moves.
- **`src/kaleta/views/budget_plan/page.py`** — deleted. Its only importer was
  the package `__init__`, which now redirects instead; the body moved to
  `panel.py` (above), so the standalone page module is dead and is removed.
- **`src/kaleta/views/budget_plan/__init__.py`** — the `/budget-plan` route
  returns `RedirectResponse("/budgets?tab=plan")` (302), the same server-side
  pattern as `views/change_password.py:36`. The route stays registered for one
  release (grace period); slice 2 removes it.
- **`src/kaleta/views/budgets/page.py`** — add a third `Plan` tab
  (`ui.tab(t("budgets.tab_plan"), icon="edit_note")`) whose panel awaits
  `render_plan_panel()`. Read `?tab=` from
  `ui.context.client.request.query_params` to pick the initial tab
  (`overview` default — unchanged from today —, `realization`, or `plan`);
  an unknown/absent value falls back to the current default (Overview). The
  Plan tab brings its own toolbar (month/year selectors), so `_render_tab_controls`
  renders nothing extra for it in this slice.
- **`src/kaleta/views/layout.py`** — remove the `("edit_note", "/budget-plan",
  "nav.budget_plan")` sidebar entry; `/budgets` remains the single budgets
  destination.
- **`src/kaleta/i18n/locales/{en,pl}.json`** — add `budgets.tab_plan`
  ("Plan" / "Plan"). The `nav.budget_plan` key is left in place (no longer
  referenced from nav) to avoid touching unrelated strings this slice.
- **`docs/bdd.md`** — new `KAL-BUD-018` scenario: the Budgets page shows a Plan
  tab with the planning grid, and `/budget-plan` redirects onto it. `@automated`.
- **`tests/e2e/`** — the Budget-Plan / annual-planning suites that `goto`
  `/budget-plan` now follow the 302 to `/budgets?tab=plan`; keep them green
  (adjust selectors only where the tab host changed the DOM, never by loosening
  an assertion). New e2e covering `KAL-BUD-018`.

## Not in scope (slice 2+)

- Shared **page-level month selector** synced across Plan and Realization —
  this slice keeps the Plan tab's own toolbar and the Realization tab's own
  month/year selectors independent.
- **Edit-pencil jump** from a Realization row to the Plan tab with that
  category focused.
- **Alt+1 / Alt+2** (and a Plan accelerator) tab-switch keyboard shortcuts.
- **Removing** the `/budget-plan` route — it stays as a 302 shim this release.
- Changing the **default tab** to Realization (the draft's open question #1);
  default stays Overview, as today, so this slice changes no landing behaviour.
- Any change to the planning editor's model or the grid/toolbar internals.
- **Lazy tab rendering.** This slice awaits all three panels eagerly at build
  (the same pattern Overview/Realization already use), so a `/budgets` visit
  builds the full planning grid even when Overview is active — extra load and
  duplicated label text (e.g. a second "Planned") in the hidden panel. Slice 2
  should build the Plan panel on first activation instead. (reviewer nit,
  non-blocking.)

## Acceptance criteria

- `grep -q 'tab_plan' src/kaleta/i18n/locales/en.json`
- `grep -q 'render_plan_panel' src/kaleta/views/budgets/page.py`
- `grep -q 'RedirectResponse' src/kaleta/views/budget_plan/__init__.py`
- `test -z "$(grep -n '"/budget-plan"' src/kaleta/views/layout.py)"`
- `grep -q 'KAL-BUD-018' docs/bdd.md`
- `uv run python scripts/spec_coverage.py`
- `./scripts/verify.sh --e2e` passes (views change — rule 8; the Budget-Plan
  e2e suites are the guard that the redirect + embed preserved the editor).

## Touchpoints

`src/kaleta/views/budget_plan/panel.py` (new),
`src/kaleta/views/budget_plan/page.py`,
`src/kaleta/views/budget_plan/__init__.py`,
`src/kaleta/views/budgets/page.py`, `src/kaleta/views/layout.py`,
`src/kaleta/i18n/locales/en.json`, `src/kaleta/i18n/locales/pl.json`,
`docs/bdd.md`, `tests/e2e/`.

## Open questions

Resolved from the umbrella draft for this slice:
- **Default tab** stays Overview (no landing-behaviour change); the draft's
  move to Realization is left for the slice that also adds the shared selector.
- **Redirect vs remove `/budget-plan`**: redirect (302) this slice, remove next
  — one release of grace, matching the draft's plan.

## Implementation notes

- **Panel extraction.** `budget_plan_page()` split cleanly: its body (state dict,
  `EditDialogs`, `build_plan_grid`, `render_toolbar`, `await plan_grid()`) is
  content-only, so it moved verbatim into `render_plan_panel()` in a new
  `budget_plan/panel.py`; only the `page_layout` wrapper was dropped. The old
  `budget_plan/page.py` had no other importer than its own package `__init__`,
  so it was deleted rather than left as dead code (rule 9 hygiene).
- **Initial-tab selection order.** `_render_tab_controls()` reads `tabs.value`,
  and it is called once at build time *before* `ui.tab_panels`. So the initial
  tab is fixed with `tabs.set_value(initial_tab)` right after the tab objects
  are created and before that first control render — otherwise the tab row,
  the inline control, and the active panel could disagree on first paint. The
  Plan branch of `_render_tab_controls()` returns early (the panel carries its
  own toolbar), so no stray control renders over the grid.
- **Query param.** `?tab=` is read via `ui.context.client.request.query_params`
  (the same accessor `layout.py` uses for the current path), guarded for a
  missing client/request. Only `plan` and `realization` are honoured; anything
  else (including no param) keeps the Overview default, so landing behaviour is
  unchanged except for the explicit deep-links.
- **Redirect is server-side.** `/budget-plan` returns
  `RedirectResponse("/budgets?tab=plan")` (302) from the `@ui.page` route — the
  `change_password.py` pattern — so `page.goto("/budget-plan")` in the e2e
  follows it and the URL assertion sees `/budgets?tab=plan`.
- **E2e fallout, all real (no loosened assertions).** The two `test_budget_plan`
  tests that asserted a "Budget Plan" page title now assert the redirect URL
  instead (the title is "Budgets"); the grid-content assertions are unchanged
  and still prove the editor renders. `test_navigation` dropped its
  `("Annual Plan", "/budget-plan")` nav row because the sidebar entry is gone.
  The other `/budget-plan` gotos (vs-actual, comparisons) follow the redirect
  onto the active Plan tab and needed no change. Full `./scripts/verify.sh --e2e`
  green: 266 e2e passed (incl. the new KAL-BUD-018), spec_coverage 405 covered.

## Implementation

Landed on 2026-10-21 (PR #322).

| SHA | Author | Date | Message |
|---|---|---|---|
| `a3e534d` | Dawid Adamski | 2026-10-21 | Merge pull request #322 from DawidAdamski/feat/budgets-unification-slice-1 |

**Files changed:**
- docs/architecture.md
- docs/bdd.md
- docs/plans/budgets-unification-slice-1.md
- docs/plans/chores.md
- src/kaleta/i18n/locales/en.json
- src/kaleta/i18n/locales/pl.json
- src/kaleta/views/budget_plan/__init__.py
- src/kaleta/views/budget_plan/panel.py
- src/kaleta/views/budgets/page.py
- src/kaleta/views/layout.py
- tests/e2e/test_budget_plan.py
- tests/e2e/test_navigation.py

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| `grep -q 'tab_plan' src/kaleta/i18n/locales/en.json` | 0 |
| `grep -q 'render_plan_panel' src/kaleta/views/budgets/page.py` | 0 |
| `grep -q 'RedirectResponse' src/kaleta/views/budget_plan/__init__.py` | 0 |
| `test -z "$(grep -n '"/budget-plan"' src/kaleta/views/layout.py)"` | 0 |
| `grep -q 'KAL-BUD-018' docs/bdd.md` | 0 |
| `uv run python scripts/spec_coverage.py` | 0 |
| `./scripts/verify.sh --e2e` | skipped (--fast); green at PR #322 merge |

**Notes:** Touchpoint overlap is full (script's partial-coverage warning was a false positive). Heavy e2e criteria were not re-run at archive time; they were green at merge.
