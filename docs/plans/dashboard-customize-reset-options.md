---
plan_id: dashboard-customize-reset-options
title: Dashboard — Split Reset into "Reset layout" and "Reset widgets"
area: dashboard
effort: small
roadmap_ref: ../roadmap.md#dashboard
status: in-progress
deferred_to: q4-2026
---

# Dashboard — Split Reset into "Reset layout" and "Reset widgets"

## Intent

Today the Customize dialog has a single `Reset to default` button
that does two things at once: it re-enables every disabled widget
*and* restores every widget's default size and position. A user who
intentionally disabled half the widgets but messed up the layout of
the remaining half can't recover the grid without bringing back
widgets they don't want.

Split the reset into two discrete actions so each concern is
addressable on its own.

## Scope

- In the Customize dialog, replace the single `Reset to default`
  button with **two buttons**:
  - **`Reset layout`** — keeps the current *enabled set*, but
    restores each enabled widget to its `default_size` and puts them
    back in `DEFAULT_WIDGETS` order (filtered to only enabled ones).
    Writes the new list to `app.storage.user["dashboard_layout"]`.
  - **`Reset widgets`** — restores *everything*: every widget in
    `DEFAULT_WIDGETS` is enabled, each at its `default_size` in the
    canonical order. Equivalent to today's Reset.
- **Confirmation** — neither reset asks for confirmation (they're
  cheap, undoable by toggling widgets back off).
- **Labels in both locales** — EN and PL added; tooltips spell out
  what each does in one sentence.
- **Customize hint** reworded to mention both resets so new users
  understand the difference.

Out of scope:
- Undo / redo for reset actions.
- A "Reset this widget" per-row action.
- Separate reset buttons in Edit mode (the dashboard itself).

## Acceptance criteria

- Given a user has toggled off `net_worth_trend` and resized
  `cashflow_chart` to `(2, 2)`: clicking **Reset layout** leaves
  `net_worth_trend` disabled but brings `cashflow_chart` back to
  `(4, 2)` at its canonical position among enabled widgets.
- Same starting state, clicking **Reset widgets** re-enables
  `net_worth_trend` and restores every widget to
  `DEFAULT_WIDGETS` × `default_size`.
- Existing unit tests pass; new tests cover
  `_reset_layout_keep_enabled(layout)` and
  `_reset_layout_full_defaults()`.

## Touchpoints

- `src/kaleta/views/dashboard.py`:
  - `_open_customize_dialog` — remove `_reset`, add
    `_reset_layout` (keep-enabled) and `_reset_widgets`
    (full-defaults).
  - Rework the bottom button row: `Reset layout | Reset widgets`
    on the left, `Cancel | Save` on the right.
- `src/kaleta/i18n/locales/{en,pl}.json`:
  - `dashboard_widgets.reset_layout`, `reset_layout_hint`,
    `reset_widgets`, `reset_widgets_hint`, `reset_layout_done`.
  - Remove the old `reset` / `reset_done` keys.
- `tests/unit/views/test_dashboard_layout.py` — add the two reset
  helpers.

## Open questions

1. **Which button's visual weight is primary?** Default: both `flat`
   with the same colour — neither is scary.
2. **Should `Reset layout` also clear the legacy
   `dashboard_widgets` key?** Default: **yes**, same as today.

## Implementation notes

### Open questions — resolved

1. **Which button's visual weight is primary?** Default taken: **neither**.
   Both are `flat color=grey-7`, the styling the single `Reset to default`
   button already had, sitting together on the left of the dialog footer.
2. **Should `Reset layout` also clear the legacy `dashboard_widgets` key?**
   Default taken: **yes**. Both resets go through one `_apply_reset()` helper
   that writes `dashboard_layout` and pops the legacy id-only key, exactly as
   the old single reset did.

### Decisions a reviewer should know

- **Two helpers, both pure.** `_reset_layout_keep_enabled(layout)` and
  `_reset_layout_full_defaults()` live at module scope in `dashboard.py`
  (next to `_validate_layout`, which the same test module already imports)
  so they are unit-testable without a NiceGUI client. The dialog callbacks
  are thin wrappers over them.
- **`credit_utilization` is registered but not in `DEFAULT_WIDGETS`.** It is
  an opt-in extra a user can switch on from the Customize dialog. A *layout*
  reset must not disable it, but `DEFAULT_WIDGETS` has no canonical position
  to offer it — so `_reset_layout_keep_enabled` emits the canonical block
  first (`DEFAULT_WIDGETS` order, filtered to enabled) and then any enabled
  extras in their current relative order, each at its `default_size`.
  Covered by `test_non_default_widget_stays_enabled_after_the_canonical_block`.
- **Empty layout in, empty layout out.** The helper is a pure transform. It
  is unreachable from the dialog (the Save path's `min_one` guard and
  `resolve_user_layout` both prevent an empty stored layout), and the read
  path already substitutes the defaults for an empty list, so the helper does
  not second-guess it.
- **One extra i18n key beyond the plan's list.** Touchpoints named
  `reset_layout_done` but not a counterpart for the full reset, while also
  asking for the old `reset_done` to be removed — that would leave the
  widgets reset without a confirmation, or make both resets say the same
  thing. Added `reset_widgets_done` ("Dashboard reset to defaults.", the old
  `reset_done` string) so the two actions confirm distinctly. `reset` and
  `reset_done` are gone from both locales; no other call site referenced them.
- **`data-customize-row` on each dialog row** — a one-attribute production
  hook (Working Agreement §3), mirroring the `data-widget-id` the grid
  wrapper already carries, so the e2e test targets a widget's checkbox by id
  rather than by row index.
- **BDD.** There was no Dashboard feature in `docs/bdd.md` at all, so
  `## Feature: Dashboard Customization` is new, with KAL-DSH-001 /
  KAL-DSH-002 tagged `@automated` and covered by
  `tests/e2e/test_dashboard_customize.py`. The e2e test sets up the
  scenario's exact preconditions — `net_worth_trend` toggled off via the
  dialog, `cashflow_chart` cycled 4x2 → 4x3 → 2x2 through the same
  `window.__kaletaCycleDashSize` hook the edit-mode resize button calls —
  and asserts on `data-cols` / `data-rows`. It ends on `Reset widgets`, so it
  leaves the shared e2e session's dashboard back at defaults for later tests.
- **`Reset layout` reads the live checkboxes, not the opening snapshot.**
  First cut closed over `current_layout` (the layout as of dialog open), so a
  widget unticked in the same session and then reset — without pressing Save —
  came back, contradicting the button's own tooltip. Both `_save` and
  `_reset_layout` now derive the enabled set from the same `enabled` dict the
  checkboxes mutate, and `_reset_layout` gained the `min_one` guard `_save`
  already had. Caught by `review_gate.sh`; regression-covered by KAL-DSH-003.
- **No toast assertions in e2e.** Both resets call `ui.navigate.to("/")`
  immediately after `ui.notify`, so waiting on the confirmation is a race.
  The resulting grid is asserted instead; the `_done` strings are covered by
  review, not by a flaky wait.
