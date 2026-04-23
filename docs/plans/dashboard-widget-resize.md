---
plan_id: dashboard-widget-resize
title: Dashboard — Grid-based widget resize and any-to-any reorder
area: dashboard
effort: medium
status: draft
roadmap_ref: ../roadmap.md#dashboard
---

# Dashboard — Grid-based widget resize and any-to-any reorder

## Intent

Today the dashboard renders widgets in three size-segregated containers
(KPI row, half grid, full stack). Edit mode lets users drag within each
container, but cross-size reorder is blocked and widgets can't be
resized at all — `net_worth_trend` is stuck small; `cashflow_chart`
can't shrink to half-width. The user wants both:

1. Swap *any* widget with *any* widget regardless of current size.
2. Resize a widget — e.g. promote a small KPI tile into a
   `2×2` square, or stretch a chart from `4×2` to `4×3`.

Treat those as one mechanism: **a formal cell grid**. Every widget
occupies a rectangle `(cols, rows)` in a 4-column CSS grid. Dragging
into a different part of the grid reorders; clicking a resize button
cycles through the widget's declared `allowed_sizes`. Both gestures
post the new layout to the server, which persists it per user.

## Scope

- **Unified 4-column CSS grid** replaces the KPI row / half grid /
  full stack. `grid-template-columns: repeat(4, 1fr)` at desktop
  width; rows auto-size (`grid-auto-rows: minmax(120px, auto)` or
  similar). On narrow viewports the columns collapse (media query) —
  keep the responsive fallback simple.
- **Each widget wrap gets `grid-column: span C; grid-row: span R`**
  where `(C, R)` is the widget's current effective size.
- **Widget catalog upgrade** — `Widget` gains:
  - `default_size: tuple[int, int]` (cols, rows).
  - `allowed_sizes: tuple[tuple[int, int], ...]` — the cycle list.
    Must include `default_size`. Single-entry = fixed size (no resize
    button rendered).
  - `render(session, is_dark, cols, rows)` — render functions gain
    two new args. Widgets can ignore them (most already size to the
    container) or branch on them.
- **Default sizes** per the agreed mapping:
  | Widget id                                                                           | default | allowed               |
  |-------------------------------------------------------------------------------------|---------|-----------------------|
  | `total_balance`, `month_income`, `month_expenses`, `month_net`, `net_worth`, `predicted_30d`, `savings_rate_kpi` | `2×1`   | `1×1, 2×1`            |
  | `budget_variance_month`, `top_merchants`, `ytd_summary`, `upcoming_planned`, `largest_transactions` | `2×2`   | `2×2, 4×2`            |
  | `cashflow_chart`, `savings_rate_trend`, `net_worth_trend`                           | `4×2`   | `2×2, 4×2, 4×3`       |
  | `quick_actions`                                                                     | `4×1`   | `4×1, 4×2`            |
  | `recent_transactions`                                                               | `4×2`   | `4×2, 4×3`            |
- **Storage** — new key `app.storage.user["dashboard_layout"]`:
  `list[{"id": str, "cols": int, "rows": int}]` in render order. The
  legacy `dashboard_widgets: list[str]` is kept for one release as a
  migration source: if `dashboard_layout` is missing but
  `dashboard_widgets` exists, the server upgrades it by mapping each
  widget id to its `default_size`.
- **Single SortableJS instance** on the unified grid. Drag any card
  to any slot; SortableJS reorders DOM, the onEnd handler posts the
  new layout. No size-group filtering (the grid takes all sizes).
- **Resize button** in edit mode — small circular icon next to the
  drag-indicator icon. Tooltip names the next size. Click cycles
  through `allowed_sizes` (wraps around). Updates `grid-column-span`
  and `grid-row-span` in-place, then posts. Hidden when
  `len(allowed_sizes) == 1`.
- **Persistence endpoint** — `POST /_dashboard/layout`, Pydantic
  `_LayoutPayload` model, validates:
  - Every id exists in `WIDGETS`.
  - Every `(cols, rows)` is in the widget's `allowed_sizes`.
  - Duplicates collapsed to first occurrence.
  - Empty → falls back to stored.
- **Customize dialog** — unchanged except for one tweak: the
  existing Reset button now clears `dashboard_layout` in addition to
  `dashboard_widgets`. Checkboxes still toggle enable/disable — a
  disabled widget is absent from the layout; re-enabling appends it
  at `default_size`.

Out of scope:
- **Drag-to-resize** (grab a corner, stretch). The click-to-cycle
  approach is simpler and matches the discrete `allowed_sizes` list.
- **Arbitrary (cols, rows)** outside `allowed_sizes`. The catalog
  author decides which shapes each widget supports.
- **Mobile drag UX tuning** — SortableJS touch support works; no
  extra polish for small screens.
- **Per-widget settings** (date range, colour, etc.) — future plan.
- **Packing algorithm for holes in the grid** — CSS grid flows
  widgets in order; if a widget doesn't fit in the remaining slots
  on a row, it starts the next row. No automatic hole-filling
  (`grid-auto-flow: dense` is a nice-to-have, decide when testing).

## Acceptance criteria

- With default config, a dashboard renders into a single 4-column
  grid; no visible regression vs. today beyond the new layout.
  `dashboard_layout` is absent from storage; the server renders from
  defaults (or migrated `dashboard_widgets`).
- Enter Edit mode, drag `total_balance` onto `cashflow_chart`'s
  position. Both widgets swap; `total_balance` keeps its `2×1` size,
  `cashflow_chart` keeps its `4×2` size. Reload shows the new order.
- In Edit mode, clicking the resize button on `top_merchants`
  (default `2×2`) cycles to `4×2`; another click wraps back to `2×2`.
  Storage contains the updated `(cols, rows)` after each click.
- Posting a disallowed size to `/_dashboard/layout` returns HTTP 400
  and storage stays unchanged.
- Widgets with a single `allowed_sizes` entry don't render a resize
  button.
- Legacy users whose storage holds only `dashboard_widgets` see the
  dashboard render correctly on first load; after the first edit,
  storage is upgraded to `dashboard_layout`.
- `tests/unit/views/test_dashboard_layout.py` covers
  `_validate_layout(payload, stored)`, `_cycle_size`, and migration
  from legacy `dashboard_widgets`.
- Existing unit tests for `_merge_order` are removed along with the
  old endpoint.
- Keyboard reorder (Alt+↑/↓) still works in the unified grid.

## Touchpoints

- `src/kaleta/views/dashboard_widgets.py`:
  - Extend `Widget` dataclass with `default_size` and `allowed_sizes`.
  - Update `_register` to accept both. Apply the default-sizes table.
  - Broaden `RenderFn` signature: `(session, is_dark, cols, rows)`.
    Existing render functions accept and ignore the new args.
  - Drop `WidgetSize = Literal["kpi", "half", "full"]` in favour of
    `WidgetSize = tuple[int, int]`.
- `src/kaleta/views/dashboard.py`:
  - Single `ui.element("div")` as the grid container
    (`id="dash-grid"`), replace the three containers.
  - Per-widget wrap sets `grid-column: span C; grid-row: span R` via
    inline style or CSS variable.
  - New resize button in `_render_wrapped` (hidden when only one
    allowed size).
  - Replace `_merge_order` with `_validate_layout` that takes a list
    of `{id, cols, rows}` dicts and returns a cleaned list.
  - Replace `/_dashboard/order` with `/_dashboard/layout`. Migration
    shim reads legacy storage on first load.
  - Update `_INIT_JS` to bind one Sortable to `#dash-grid` and one
    resize-cycle helper.
- `src/kaleta/i18n/locales/{en,pl}.json`:
  - New keys: `resize_widget`, `resize_next_size` (tooltip with
    {cols}×{rows}), `layout_updated`.
  - Reword `edit_banner` slightly to mention resize.
- `tests/unit/views/`:
  - Replace `test_dashboard_order.py` with `test_dashboard_layout.py`.
  - Cases: flatten preserves order; unknown ids stripped; sizes not
    in `allowed_sizes` rejected; legacy migration from
    `dashboard_widgets`; empty payload falls back to stored.
- `docs/architecture.md`:
  - Update ADR-031 or supersede with ADR-032 describing the grid
    layout and the storage key migration.

## Open questions

1. **Grid row height** — fixed `minmax(120px, auto)` is probably
   fine; a 2-row chart becomes `240px+` tall and scales proportional
   to width. Default: **`minmax(120px, auto)` with 16px row gap**.
2. **`grid-auto-flow: dense`?** Fills holes greedily but can swap
   widget order unexpectedly. Default: **no, strict source order**,
   so what the user drags is what they see.
3. **Narrow-viewport fallback** — at < 768px collapse to 2 columns,
   at < 480px to 1 column. Widgets keep their declared
   `cols` but get clamped to the viewport width via
   `min(cols, grid-column-count)`. Default: **yes, two breakpoints**.
4. **Cycle order** — widgets with 3 allowed sizes
   (`cashflow_chart`: `2×2, 4×2, 4×3`): cycle grows through the list,
   wrapping. Default: **forward cycle**, no backward shortcut.
5. **Disabled-widget re-enable size** — when user checks a widget
   back on in Customize, what size does it render at? Default:
   **`default_size`**.
6. **Keep the legacy `/_dashboard/order` endpoint for one release?**
   Default: **no, remove it** — no external API clients rely on it
   (it's internal).
7. **Should the resize button also move the widget to the end of the
   grid to make room?** Default: **no** — resize is in-place. If the
   new size doesn't fit on the current row, CSS grid flows it to the
   next row automatically.

## Implementation notes

_Filled in as work progresses._
