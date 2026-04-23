---
plan_id: dashboard-widget-resize
title: Dashboard — Resize widgets between size groups
area: dashboard
effort: medium
status: draft
roadmap_ref: ../roadmap.md#dashboard
---

# Dashboard — Resize widgets between size groups

## Intent

Today each dashboard widget has a fixed size declared in the widget
catalog (`kpi | half | full`). A user who prefers, say, a bigger Top
Merchants card cannot promote it from `half` to `full`; a user who
wants Predicted 30-day Balance as a compact tile cannot shrink the
chart into a `kpi`. The size is the author's guess, not the user's
preference.

This plan adds per-user widget sizing on top of the existing Edit
mode. In edit mode a widget carries a resize affordance next to the
drag handle; clicking it cycles the widget through the sizes the
widget author has declared as supported. The override persists in
`app.storage.user` alongside the order. Rendering switches the widget
to the correct size group at page load; the widget's own render
function is expected to adapt to its current size (most do already).

## Scope

- **Widget catalog gains `allowed_sizes: tuple[WidgetSize, ...]`** —
  defaults to `(widget.size,)` for backwards compatibility, so any
  widget not explicitly opted-in stays fixed-size.
- **Initial coverage** — opt in the widgets that clearly read well at
  multiple sizes:
  - `predicted_30d` → `(kpi, half)`
  - `net_worth` → `(kpi, half)`
  - `savings_rate_kpi` → `(kpi, half)`
  - `budget_variance_month` → `(half, full)`
  - `top_merchants` → `(half, full)`
  - `upcoming_planned` → `(half, full)`
  - `largest_transactions` → `(half, full)`
  - `cashflow_chart` → `(half, full)`
  - `savings_rate_trend` → `(half, full)`
  - `net_worth_trend` → `(half, full)`
  - Others stay fixed at their declared size.
- **Per-widget size override** stored in
  `app.storage.user["dashboard_sizes"]: dict[str, WidgetSize]`. When a
  widget ID is absent from this dict, the default
  `widget.size` applies.
- **Resize button in edit mode** next to the drag handle. Click cycles
  through `allowed_sizes` in order. A tooltip names the current/next
  size. No drag-to-resize (too finicky in a 3-container layout).
- **Persistence endpoint** — new FastAPI POST `/_dashboard/size` that
  accepts `{widget_id, size}`, validates membership in `allowed_sizes`,
  writes to `app.storage.user["dashboard_sizes"]`. Returns 400 if the
  widget ID is unknown or the target size is not allowed.
- **Render-time routing** — when building the three size-group lists,
  a widget's effective size is
  `user_overrides.get(wid, WIDGETS[wid].size)`, and it is placed into
  the matching container.
- **Order safety on resize** — when a widget is resized, it leaves its
  previous group's order and joins the new group's end. The flat
  `dashboard_widgets` list is updated so membership and order stay
  consistent.
- **Widget-side size awareness** — each widget's render function
  accepts an optional `size: WidgetSize` argument (default = declared
  size). Widgets that support multiple sizes branch on it; fixed-size
  widgets ignore it. Migrated via a default-argument approach so
  existing renders don't change signature semantically.
- **Reset** — the Customize dialog's Reset button clears both
  `dashboard_widgets` and `dashboard_sizes`.

Out of scope:
- **Free-form grid** with arbitrary x/y/w/h coordinates.
- **Drag-to-resize** via a corner handle.
- **Dynamic grid columns** beyond the existing KPI-row / half-grid /
  full-stack layout.
- **Resizing within an ECharts/Plotly chart** (they already size to
  container width, nothing to do).
- **Per-widget settings beyond size** (date range, colour, etc.) —
  future plan.

## Acceptance criteria

- With default config, a dashboard renders exactly as before (no
  override applied). `dashboard_sizes` stays empty in storage.
- Enter Edit mode, click the resize button on `top_merchants` (half →
  full). After the click:
  - Storage contains `dashboard_sizes["top_merchants"] == "full"`.
  - `dashboard_widgets` still contains `top_merchants` but its position
    is at the end of the full-size order.
  - Reloading the page renders `top_merchants` in the full-size stack.
- Clicking resize on a widget whose `allowed_sizes` is a single entry
  is a no-op (button is disabled or the click does nothing).
- Posting a disallowed size to `/_dashboard/size` returns HTTP 400 and
  leaves storage unchanged.
- `Reset to default` in Customize clears both
  `dashboard_widgets` and `dashboard_sizes`.
- Widgets that declare a single `allowed_sizes` render at their old
  fixed size with no visual regression.
- Existing unit tests pass; new tests cover
  `_apply_size_override(order, sizes) -> (kpi, half, full)` and
  `_cycle_size(current, allowed)`.
- Keyboard reorder (Alt+↑/↓) still works after a widget has been
  resized into a new group.

## Touchpoints

- `src/kaleta/views/dashboard_widgets.py`:
  - `Widget` dataclass: add `allowed_sizes: tuple[WidgetSize, ...]`
    with a default (`lambda size: (size,)`) via `__post_init__` or
    `field(default_factory=...)`.
  - `_register` gets an optional `allowed_sizes` argument.
  - Opt in the widgets listed in Scope.
  - `RenderFn` signature grows an optional `size: WidgetSize`
    parameter. Existing widgets accept it and ignore it.
- `src/kaleta/views/dashboard.py`:
  - New helpers `_effective_size(wid, sizes)`,
    `_group_widgets(order, sizes)`, `_cycle_size(current, allowed)`.
  - Render loop switches to grouping by *effective* size.
  - Each `_render_wrapped` call passes the effective size to
    `widget.render`.
  - New resize button in the edit-mode overlay (same corner as drag
    handle or stacked).
  - `_register_size_endpoint()` for `/_dashboard/size`.
- `src/kaleta/i18n/locales/{en,pl}.json`:
  - `resize_widget`, `resize_to_kpi`, `resize_to_half`,
    `resize_to_full`, `resize_unavailable`.
- `tests/unit/views/test_dashboard_order.py` (extend) or new file
  `test_dashboard_size.py`:
  - Cycle-size logic, size-override grouping, invalid-size rejection.
- `docs/architecture.md` — amend ADR-031 or add ADR-032 covering the
  size-override store and the resize cycle pattern.

## Open questions

1. **Cycle order vs. dropdown?** A single button that cycles feels
   fast for 2-entry `allowed_sizes` but awkward for 3-entry. Default:
   **cycle button**; if any widget ever declares all three sizes,
   revisit with a small popup menu.
2. **Resize UI placement** — same corner as drag handle (stacked), or
   opposite corner? Default: **stacked top-right**; the drag handle
   goes slightly lower, the resize button above it. Test visually.
3. **Should a fixed-size widget show a disabled button, or no button
   at all?** Default: **no button** — keeps the card visually quiet
   for the majority case.
4. **Cross-size drag-and-drop** — with resize available, should we
   also relax the Sortable group isolation so users can drag a widget
   into a different size group (implicitly resizing it)? Default:
   **no** — keeps two concerns separated; drag = reorder, click = resize.
5. **What if a widget's `allowed_sizes` shrinks in a future release
   (author removes a size)?** A stored override pointing to the
   removed size should silently fall back to `widget.size`.
   Default: **yes, fall back silently**; no migration.
6. **Should the default `allowed_sizes` include the existing
   `widget.size`?** Default: **yes** — any opt-in must also list the
   default size, otherwise an override only blocks the default.

## Implementation notes

_Filled in as work progresses._
