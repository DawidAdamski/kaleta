---
plan_id: dashboard-customize-reset-options
title: Dashboard — Split Reset into "Reset layout" and "Reset widgets"
area: dashboard
effort: small
roadmap_ref: ../roadmap.md#dashboard
status: draft
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
_Filled in as work progresses._
