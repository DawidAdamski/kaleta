---
plan_id: dashboard-chart-fluid-height
title: Dashboard — Chart widgets honour grid row span
area: dashboard
effort: small
roadmap_ref: ../roadmap.md#dashboard
status: draft
---

# Dashboard — Chart widgets honour grid row span

## Intent

Chart widgets on the dashboard (`cashflow_chart`,
`savings_rate_trend`, `net_worth_trend`) declare
`allowed_sizes = ((2, 2), (4, 2), (4, 3))`. Clicking the resize
button in Edit mode cycles through those values — the grid
re-allocates column and row span — but the echart canvas inside
each card uses a fixed Tailwind height class (`h-56` / `h-64`),
so two of the three allowed sizes look identical on screen.

Make the chart fill its grid cell. The row-span is the user's
declaration of how tall they want the chart; the renderer should
honour it.

## Scope

- Remove fixed `h-XX` classes from the `ui.echart(...)` calls in
  every chart widget and replace them with `h-full w-full`. The
  widget's outer `.dash-widget-wrap` already has
  `grid-row: span N`, so `h-full` makes the chart inherit the
  correct height.
- Ensure the widget's inner card uses `display: flex;
  flex-direction: column` so the echart can expand to fill
  remaining vertical space below the title row.
- Minimum chart height — `min-height: 180px` on the chart
  element so a `2×2` card with a tall-ish title row still
  leaves useful chart area.
- **Echart resize** — echart auto-resizes on window events but
  may not detect a grid-span change without an explicit
  `chart.resize()` call. Add a `ResizeObserver` on the widget
  wrap that dispatches to the echart instance when dimensions
  change.
- Confirm the fix visually for all three chart widgets at all
  three allowed sizes.

Out of scope:
- Changing the chart type or styling at small sizes (e.g. hiding
  axis labels when compact). Defer to a follow-up if it looks bad.
- Non-chart widgets — KPIs and list widgets already size
  correctly.
- Making the chart title / subtitle optional.

## Acceptance criteria

- In Edit mode, cycling `cashflow_chart` through
  `(2, 2) → (4, 2) → (4, 3)` makes the chart visibly taller at
  `(4, 3)` vs `(4, 2)` and visibly narrower at `(2, 2)` vs
  `(4, 2)`. All three states render the full chart, not a
  cropped view.
- Resizing the viewport triggers an echart redraw so the chart
  doesn't overflow or collapse.
- `savings_rate_trend` and `net_worth_trend` behave the same.
- No regression in default (first-load) rendering.

## Touchpoints

- `src/kaleta/views/dashboard_widgets.py`:
  - `_cashflow_chart`, `_savings_rate_trend`, `_net_worth_trend`
    (and any other chart widget) — drop `h-56`/`h-64`, add
    `h-full w-full min-h-[180px]`.
  - Helper `_section_card` already returns a card; add
    `flex flex-col` to the wrap so children stretch.
- `src/kaleta/views/dashboard.py`:
  - Extend `_INIT_JS` with a `ResizeObserver` block that walks
    `#dash-grid [data-widget-id]` and calls
    `echarts.getInstanceByDom(el).resize()` on dimension change.
    Fall back silently if the instance isn't an echart.

## Open questions

1. **Per-widget size-aware rendering?** E.g. at `(2, 2)` hide
   axis labels. Default: **no** for v1; measure first.
2. **Default chart min-height** — `180px` vs `160px`?
   Default: **180**.
3. **Echart resize trigger** — ResizeObserver on the wrap, or on
   the echart div itself? Default: **on the wrap** so it fires
   when `grid-row` span changes.

## Implementation notes
_Filled in as work progresses._
