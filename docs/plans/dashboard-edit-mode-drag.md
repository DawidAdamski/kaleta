---
plan_id: dashboard-edit-mode-drag
title: Dashboard — Edit mode with drag-and-drop reorder
area: dashboard
effort: medium
status: in-progress
roadmap_ref: ../roadmap.md#dashboard
---

# Dashboard — Edit mode with drag-and-drop reorder

## Intent

The current Customize dialog on `/` lets the user toggle widgets and
reorder them via per-row `arrow_upward` / `arrow_downward` buttons. Two
problems make it effectively unusable:

1. **Arrow-based reorder is slow.** Moving a widget from the bottom of
   a 10-item list to the top is 9+ clicks, with the dialog re-rendering
   between each. Users give up.
2. **The reorder is partly a lie.** The dashboard renders widgets in
   three separate containers grouped by `size` (KPI row → half-width
   grid → full-width stack). Cross-size moves in the dialog don't
   change the rendered order, so the user clicks up-arrow for nothing
   and concludes "Customize nie działa".

This plan replaces both problems with an **Edit mode** on the
dashboard itself. A toggle button flips the page into a mode where
each widget card grows a drag handle and users reorder by grabbing the
card and dropping it where they want. When locked again, drag handles
disappear and the dashboard is visually clean.

## Scope

- **Edit / Lock toggle.** A single button in the dashboard header,
  next to (or replacing) today's Customize button. Default state:
  locked. Label flips between `Edit layout` and `Done` (or similar).
  State is not persisted — always starts locked on page load.
- **Per-widget drag handle in edit mode.** A subtle `drag_indicator`
  icon appears on each widget card. Cards also get a light outlined
  ring / dashed border to signal "interactive".
- **Drag-and-drop reorder within each size group.** SortableJS wired
  via `ui.add_head_html` + a small JS bridge that calls a NiceGUI
  endpoint with the new order. KPI, half, and full are three
  independent sortable groups — dragging a KPI into the halves
  section is not possible (matches the layout truth).
- **Dialog stays for enable / disable + reset.** The existing
  Customize dialog retains the checkbox column and Reset button, but
  its arrow-up / arrow-down buttons are **removed**; the dialog's
  purpose becomes "what widgets exist" rather than "what order". A
  short hint points the user to Edit mode for reordering.
- **Persistence.** Same storage slot (`app.storage.user["dashboard_widgets"]`).
  Every drop event writes the new ordered list. No explicit Save in
  edit mode — drops auto-persist.
- **Keyboard accessibility.** When a widget card is focused, `Alt+↑`
  / `Alt+↓` moves it up / down within its size group. Keeps the
  current arrow-button UX for users who don't want to drag.
- **Empty-state.** If a size group is empty (user disabled every KPI
  widget), show a small placeholder card in edit mode only: "No KPI
  widgets — open Customize to add one." Hidden when locked.

Out of scope:
- **Resizing widgets** (half ↔ full, changing `size` at runtime).
- **Free-form grid** (x/y coordinates, custom widths, CSS grid
  templates). We keep the current KPI / half / full layout.
- **Cross-device sync.** `app.storage.user` is per-browser-session as
  today; no central user preferences table.
- **Widget-level settings** (date range per widget, etc.).
- **Animations beyond SortableJS defaults.**
- **Touch drag on mobile** — SortableJS supports it but we don't
  commit to tuning it; fall back to Alt+↑/↓ or the dialog.

## Acceptance criteria

- With a default dashboard, clicking `Edit layout` shows a drag handle
  on every widget; clicking `Done` hides handles and the dashboard
  renders identically to before.
- In edit mode, grabbing `predicted_30d` (KPI) and dropping it before
  `total_balance` reloads the dashboard with `predicted_30d` in the
  first slot of the KPI row. Refreshing the page preserves the new
  order.
- In edit mode, dragging a `half`-sized widget into the KPI row is
  rejected (SortableJS `group` isolation) — the widget snaps back.
- `app.storage.user["dashboard_widgets"]` after each drop contains
  exactly the widgets that were enabled before the drop, in the new
  order; disabled widgets are not added by the reorder.
- Opening Customize dialog in any state shows only the
  enable/disable checkboxes + Reset; the arrow-up / arrow-down
  buttons no longer render.
- Alt+↑ on a focused widget card moves it up one slot within its
  size group; at the top, it's a no-op. Alt+↓ mirrors this.
- Edit mode visual: each card gains a 1-px dashed outline in
  edit mode, plus a cursor:grab on the handle; in locked mode there
  is no outline and no cursor change.
- Polish and English strings exist for every new label
  (`edit_layout`, `done_editing`, `drag_hint`, empty-state placeholder,
  `customize_hint` reworded).

## Touchpoints

- `src/kaleta/views/dashboard.py`:
  - Header row: add `Edit layout` ↔ `Done` toggle button, keep the
    existing `Customize` button next to it.
  - Render-time: pass an `is_editing: bool` into the widget loop;
    when true, wrap each card with a `ui.element("div").classes("...outline-dashed...")`
    and prepend a `drag_indicator` handle.
  - Attach a Sortable instance per container
    (`kpi_row`, `halves_grid`, `fulls_stack`) with a stable DOM id.
- **New**: `src/kaleta/views/dashboard_sortable.py` (or inline in
  `dashboard.py`) — a small helper that `ui.add_head_html`s the
  SortableJS CDN script once, then emits the per-container
  `new Sortable(...)` calls with an `onEnd` callback that POSTs the
  new order to a NiceGUI endpoint.
- **Bridge endpoint**: a `@ui.page` or an `app.post("/dashboard/order")`
  handler that accepts `{kpi: [...], half: [...], full: [...]}` and
  writes the merged list back to `app.storage.user["dashboard_widgets"]`.
  Alternatively use `ui.run_javascript` in reverse via `emit` — pick
  whichever ends up simpler after a quick spike.
- `src/kaleta/views/dashboard.py::_open_customize_dialog`:
  - Remove the arrow-up / arrow-down buttons and `_swap`.
  - Reword `customize_hint` → "Toggle widgets on/off. To reorder,
    use Edit layout."
  - Keep the Reset button and the checkbox column exactly as today.
- `src/kaleta/i18n/locales/en.json` + `pl.json`:
  - Add `dashboard_widgets.edit_layout`, `done_editing`,
    `drag_hint`, `empty_size_group`.
  - Reword `customize_hint`.
- `tests/unit/views/test_dashboard.py` (or new):
  - Unit-test the endpoint that merges a new per-group order back
    into `app.storage.user`: given `{kpi:[A,B], half:[C], full:[D,E]}`
    and WIDGETS metadata, result is `[A,B,C,D,E]`.
  - Unit-test that widgets disabled before the drop stay excluded
    after the drop.
- No model, migration, schema, or service changes. No JSON file
  moves.

## Open questions

1. **One button or two?** Keep Customize + Edit as separate buttons,
   or fold them into one button that opens a menu (`Customize… ▾`)
   with two options? Default: **two buttons** — Edit is used far
   more than the add/remove dialog and deserves one-click access.
2. **Persist edit mode across reloads?** Tempting ("user was last
   editing, keep it open"), but risks leaving every user in edit
   mode forever and cluttering the default view. Default: **no** —
   edit mode always starts `false` on page load.
3. **Which Sortable library?** SortableJS (MIT, ~15 KB, battle-tested,
   vanilla JS) vs. Quasar's own `QSortable` via NiceGUI. Default:
   **SortableJS** — Quasar's sortable list is row-oriented and
   doesn't handle our grid/row mix cleanly; SortableJS is grid-aware.
4. **How do we round-trip the order from JS to Python?** NiceGUI
   offers a few patterns: `ui.run_javascript` (JS → Python via
   `.emit()`), a plain FastAPI POST, or a hidden
   `ui.input` bound to a string that JS mutates. Default: **FastAPI
   POST** (`app.post("/_dashboard/order")`) since it's the most
   explicit and easy to unit-test.
5. **Should drops also close the Customize dialog if open?** If the
   user is reordering via Edit mode while the dialog is open, the
   dialog's widget-list becomes stale. Default: **close the dialog
   when entering edit mode** — only one reorder affordance is live
   at a time.
6. **What about the `quick_actions` widget (full-size but action-y)?**
   Still draggable; no special-case. A user who wants it at the top
   can drop it at the top of the full-size stack. (Won't jump to
   KPI — different size group.)
7. **Visual cue for edit mode beyond per-card outline?** A thin
   banner (`You're editing — drag cards to reorder. Done`) at the
   top of the grid? Default: **yes, short banner** — cheap, and
   makes the mode transition unambiguous.

## Implementation notes

_Filled in as work progresses._
