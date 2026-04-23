"""Dashboard Command Center.

Renders a unified 4-column CSS grid of widgets. The widget catalog lives
in ``dashboard_widgets.py``; every widget declares a ``default_size``
and ``allowed_sizes`` as ``(cols, rows)`` tuples. The dashboard:

* Places each widget with ``grid-column: span C; grid-row: span R``.
* Runs a single SortableJS instance on the grid so the user can drag
  any card onto any slot.
* Renders a resize button (in edit mode) that cycles a widget through
  its ``allowed_sizes`` in place.

The full layout — widget order *and* per-widget size — is persisted in
``app.storage.user["dashboard_layout"]`` as a list of
``{id, cols, rows}`` dicts.
"""

from __future__ import annotations

from typing import Any

from nicegui import app, ui
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.db import AsyncSessionFactory
from kaleta.i18n import t
from kaleta.views.dashboard_widgets import (
    DEFAULT_WIDGETS,
    WIDGETS,
    Widget,
    default_layout,
    resolve_user_layout,
)
from kaleta.views.layout import page_layout
from kaleta.views.theme import PAGE_TITLE

_GRID_COLUMNS = 4

_SORTABLE_SCRIPT = '<script src="/static/vendor/sortable.min.js"></script>'

_EDIT_MODE_STYLE = f"""
<style>
  #dash-grid {{
    display: grid;
    grid-template-columns: repeat({_GRID_COLUMNS}, minmax(0, 1fr));
    grid-auto-rows: minmax(120px, auto);
    gap: 16px;
    width: 100%;
  }}
  @media (max-width: 768px) {{
    #dash-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .dash-widget-wrap {{
      grid-column: span min(var(--cols), 2) !important;
    }}
  }}
  @media (max-width: 480px) {{
    #dash-grid {{ grid-template-columns: 1fr; }}
    .dash-widget-wrap {{ grid-column: span 1 !important; }}
  }}
  .dash-widget-wrap {{
    position: relative;
    grid-column: span var(--cols);
    grid-row: span var(--rows);
    min-height: 0;
  }}
  .dash-widget-wrap > :not(.dash-drag-handle-icon):not(.dash-resize-btn) {{
    height: 100%;
  }}
  .dash-widget-wrap .dash-drag-handle-icon,
  .dash-widget-wrap .dash-resize-btn {{
    position: absolute; top: 6px; z-index: 5;
    display: none;
    padding: 2px 4px;
    border-radius: 6px;
    color: #64748b;
    background: rgba(148,163,184,0.14);
  }}
  .dash-widget-wrap .dash-drag-handle-icon {{
    right: 6px;
    pointer-events: none;
  }}
  .dash-widget-wrap .dash-resize-btn {{
    right: 36px;
    cursor: pointer;
  }}
  .dash-widget-wrap .dash-resize-btn:hover {{
    background: rgba(148,163,184,0.28);
  }}
  body.dash-editing .dash-widget-wrap {{
    outline: 1px dashed rgba(100,116,139,0.45);
    outline-offset: 4px;
    border-radius: 10px;
    cursor: grab;
  }}
  body.dash-editing .dash-widget-wrap:active {{ cursor: grabbing; }}
  body.dash-editing .dash-widget-wrap .dash-drag-handle-icon,
  body.dash-editing .dash-widget-wrap .dash-resize-btn {{
    display: block;
  }}
  body.dash-editing .dash-widget-wrap:focus-visible {{
    outline: 2px solid rgb(59,130,246);
  }}
  .dash-edit-banner {{ display: none; }}
  body.dash-editing .dash-edit-banner {{ display: flex; }}
  .sortable-ghost {{ opacity: 0.3; }}
  .sortable-chosen {{ cursor: grabbing; }}
</style>
"""

_INIT_JS = """
<script>
window.__kaletaInitDashSortable = function() {
  if (typeof Sortable === 'undefined') {
    console.warn('[dashboard] Sortable not ready, retrying in 150ms');
    setTimeout(window.__kaletaInitDashSortable, 150);
    return;
  }
  const container = document.getElementById('dash-grid');
  if (!container) return;
  if (container.__sortable) {
    container.__sortable.destroy();
    container.__sortable = null;
  }
  if (!document.body.classList.contains('dash-editing')) return;
  container.__sortable = new Sortable(container, {
    draggable: '.dash-widget-wrap',
    animation: 150,
    ghostClass: 'sortable-ghost',
    chosenClass: 'sortable-chosen',
    onEnd: () => window.__kaletaPostDashLayout(),
  });
  console.debug('[dashboard] Sortable initialised, editing =',
    document.body.classList.contains('dash-editing'));
};
window.__kaletaPostDashLayout = function() {
  const entries = Array.from(
    document.querySelectorAll('#dash-grid [data-widget-id]')
  ).map(e => ({
    id: e.dataset.widgetId,
    cols: parseInt(e.dataset.cols, 10) || 1,
    rows: parseInt(e.dataset.rows, 10) || 1,
  }));
  fetch('/_dashboard/layout', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({entries}),
  }).catch(err => console.warn('[dashboard] POST layout failed', err));
};
window.__kaletaCycleDashSize = function(widgetId) {
  const wrap = document.querySelector(
    '#dash-grid [data-widget-id="' + widgetId + '"]'
  );
  if (!wrap) return;
  const allowed = JSON.parse(wrap.dataset.allowedSizes || '[]');
  if (allowed.length < 2) return;
  const current = [
    parseInt(wrap.dataset.cols, 10) || 1,
    parseInt(wrap.dataset.rows, 10) || 1,
  ];
  const idx = allowed.findIndex(s => s[0] === current[0] && s[1] === current[1]);
  const next = allowed[(idx + 1) % allowed.length];
  wrap.dataset.cols = String(next[0]);
  wrap.dataset.rows = String(next[1]);
  wrap.style.setProperty('--cols', String(next[0]));
  wrap.style.setProperty('--rows', String(next[1]));
  window.__kaletaPostDashLayout();
};
window.__kaletaToggleDashEdit = function() {
  const on = document.body.classList.toggle('dash-editing');
  const btn = document.getElementById('dash-edit-btn-label');
  if (btn) btn.innerText = on
    ? (btn.dataset.labelDone || 'Done')
    : (btn.dataset.labelEdit || 'Edit layout');
  console.debug('[dashboard] toggled edit mode, now =', on);
  window.__kaletaInitDashSortable();
};
window.__kaletaDashKbdMove = function(evt) {
  if (!evt.altKey) return;
  if (evt.key !== 'ArrowUp' && evt.key !== 'ArrowDown') return;
  const focus = document.activeElement;
  const fromTarget = evt.target && evt.target.closest
    ? evt.target.closest('.dash-widget-wrap') : null;
  const fromFocus = focus && focus.closest
    ? focus.closest('.dash-widget-wrap') : null;
  const wrap = fromTarget || fromFocus;
  if (!wrap) return;
  const parent = wrap.parentElement;
  if (!parent) return;
  evt.preventDefault();
  if (evt.key === 'ArrowUp' && wrap.previousElementSibling) {
    parent.insertBefore(wrap, wrap.previousElementSibling);
  } else if (evt.key === 'ArrowDown' && wrap.nextElementSibling) {
    parent.insertBefore(wrap.nextElementSibling, wrap);
  }
  wrap.focus();
  window.__kaletaPostDashLayout();
};
document.addEventListener('keydown', window.__kaletaDashKbdMove);
</script>
"""


class _LayoutEntry(BaseModel):
    id: str
    cols: int
    rows: int


class _LayoutPayload(BaseModel):
    entries: list[_LayoutEntry] = []


def _validate_layout(
    entries: list[dict[str, Any]], stored: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Return a cleaned layout list.

    Rules:
    - each ``id`` must exist in WIDGETS
    - ``(cols, rows)`` must be in the widget's ``allowed_sizes``
    - duplicates collapsed to first occurrence
    - empty result falls back to ``stored``
    """
    cleaned: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in entries:
        wid = entry.get("id")
        if not isinstance(wid, str) or wid not in WIDGETS or wid in seen:
            continue
        w = WIDGETS[wid]
        cols = entry.get("cols")
        rows = entry.get("rows")
        if not isinstance(cols, int) or not isinstance(rows, int):
            continue
        if (cols, rows) not in w.allowed_sizes:
            continue
        cleaned.append({"id": wid, "cols": cols, "rows": rows})
        seen.add(wid)
    return cleaned or list(stored)


def _register_layout_endpoint() -> None:
    from nicegui import app as nicegui_app

    @nicegui_app.post("/_dashboard/layout", include_in_schema=False)
    async def _save_layout(payload: _LayoutPayload) -> dict[str, str]:
        stored = resolve_user_layout(
            app.storage.user.get("dashboard_layout"),
            app.storage.user.get("dashboard_widgets"),
        )
        new_layout = _validate_layout(
            [e.model_dump() for e in payload.entries], stored
        )
        app.storage.user["dashboard_layout"] = new_layout
        return {"status": "ok"}


def register() -> None:
    _register_layout_endpoint()

    @ui.page("/")
    async def dashboard() -> None:
        is_dark: bool = app.storage.user.get("dark_mode", False)
        layout = resolve_user_layout(
            app.storage.user.get("dashboard_layout"),
            app.storage.user.get("dashboard_widgets"),
        )

        ui.add_head_html(_SORTABLE_SCRIPT)
        ui.add_head_html(_EDIT_MODE_STYLE)
        ui.add_head_html(_INIT_JS)

        with page_layout(t("dashboard.title")):
            with ui.row().classes("w-full items-center justify-between mb-2"):
                ui.label(t("dashboard.title")).classes(PAGE_TITLE)
                with ui.row().classes("items-center gap-2"):
                    with ui.button(
                        on_click=lambda: ui.run_javascript(
                            "window.__kaletaToggleDashEdit()"
                        )
                    ).props("flat color=primary"):
                        ui.icon("drag_indicator")
                        ui.label(t("dashboard_widgets.edit_layout")).props(
                            f'id="dash-edit-btn-label" '
                            f'data-label-edit="{t("dashboard_widgets.edit_layout")}" '
                            f'data-label-done="{t("dashboard_widgets.done_editing")}"'
                        )
                    ui.button(
                        t("dashboard_widgets.customize"),
                        icon="tune",
                        on_click=lambda: _open_customize_dialog(layout),
                    ).props("flat color=primary")

            with ui.row().classes(
                "dash-edit-banner w-full items-center gap-2 p-3 mb-3 rounded "
                "bg-amber-100 dark:bg-amber-900/40 "
                "text-amber-900 dark:text-amber-100 text-sm"
            ):
                ui.icon("info")
                ui.label(t("dashboard_widgets.edit_banner"))

            async with AsyncSessionFactory() as session:
                with ui.element("div").props('id="dash-grid"'):
                    for entry in layout:
                        wid = entry["id"]
                        if wid not in WIDGETS:
                            continue
                        await _render_wrapped(
                            WIDGETS[wid],
                            session,
                            is_dark,
                            entry["cols"],
                            entry["rows"],
                        )
                    if not layout:
                        _render_empty_placeholder()

            ui.run_javascript(
                "window.__kaletaInitDashSortable && window.__kaletaInitDashSortable()"
            )


async def _render_wrapped(
    widget: Widget,
    session: AsyncSession,
    is_dark: bool,
    cols: int,
    rows: int,
) -> None:
    import json

    allowed_json = json.dumps([list(s) for s in widget.allowed_sizes])
    with ui.element("div").props(
        f'data-widget-id="{widget.id}" '
        f'data-cols="{cols}" data-rows="{rows}" '
        f"data-allowed-sizes='{allowed_json}' "
        f'tabindex="0"'
    ).classes("dash-widget-wrap").style(f"--cols: {cols}; --rows: {rows}"):
        with ui.element("div").classes("dash-drag-handle-icon").props(
            f'title="{t("dashboard_widgets.drag_hint")}"'
        ):
            ui.icon("drag_indicator")
        if len(widget.allowed_sizes) > 1:
            with ui.element("div").classes("dash-resize-btn").props(
                f'title="{t("dashboard_widgets.resize_widget")}" '
                f"onclick=\"window.__kaletaCycleDashSize('{widget.id}')\""
            ):
                ui.icon("aspect_ratio")
        await widget.render(session, is_dark)


def _render_empty_placeholder() -> None:
    with ui.element("div").classes(
        "w-full p-4 text-center text-sm "
        "text-slate-500 border border-dashed border-slate-300 rounded"
    ).style(f"grid-column: 1 / span {_GRID_COLUMNS}"):
        ui.label(t("dashboard_widgets.empty_size_group"))


def _open_customize_dialog(current_layout: list[dict[str, Any]]) -> None:
    """Dialog for enabling and disabling dashboard widgets.

    Reordering and resizing happen via Edit mode on the dashboard itself;
    this dialog only manages which widgets are shown.
    """
    enabled_ids = [e["id"] for e in current_layout]
    disabled = [wid for wid in WIDGETS if wid not in enabled_ids]
    working = enabled_ids + disabled
    enabled: dict[str, bool] = {wid: (wid in enabled_ids) for wid in working}

    with ui.dialog() as dialog, ui.card().classes("min-w-96 max-w-xl"):
        ui.label(t("dashboard_widgets.customize_title")).classes(
            "text-lg font-semibold"
        )
        ui.label(t("dashboard_widgets.customize_hint")).classes(
            "text-xs text-grey-6 mb-2"
        )

        list_container = ui.column().classes("w-full gap-1 max-h-96 overflow-y-auto")

        def _toggle(widget_id: str, value: bool) -> None:
            enabled[widget_id] = value

        with list_container:
            for wid in working:
                w: Widget = WIDGETS[wid]
                with ui.row().classes(
                    "w-full items-center gap-2 p-2 rounded border border-slate-200/60"
                ):
                    cb = ui.checkbox(value=enabled[wid])
                    cb.on_value_change(
                        lambda e, _wid=wid: _toggle(_wid, bool(e.value))
                    )
                    ui.icon(w.icon).classes("text-primary")
                    ui.label(t(w.title_key)).classes("flex-1 text-sm")
                    badge_text = f"{w.default_size[0]}×{w.default_size[1]}"
                    ui.badge(badge_text).props("color=grey-6").classes("text-xs")

        def _save() -> None:
            existing = {e["id"]: e for e in current_layout}
            new_layout: list[dict[str, Any]] = []
            for wid in working:
                if not enabled.get(wid):
                    continue
                if wid in existing:
                    new_layout.append(existing[wid])
                else:
                    w = WIDGETS[wid]
                    new_layout.append(
                        {
                            "id": wid,
                            "cols": w.default_size[0],
                            "rows": w.default_size[1],
                        }
                    )
            if not new_layout:
                ui.notify(t("dashboard_widgets.min_one"), color="negative")
                return
            app.storage.user["dashboard_layout"] = new_layout
            ui.notify(t("dashboard_widgets.saved"), color="positive")
            dialog.close()
            ui.navigate.to("/")

        def _reset() -> None:
            app.storage.user["dashboard_layout"] = default_layout()
            app.storage.user.pop("dashboard_widgets", None)
            ui.notify(t("dashboard_widgets.reset_done"), color="positive")
            dialog.close()
            ui.navigate.to("/")

        with ui.row().classes("w-full justify-between items-center mt-3"):
            ui.button(
                t("dashboard_widgets.reset"), icon="restart_alt", on_click=_reset
            ).props("flat color=grey-7")
            with ui.row().classes("gap-2"):
                ui.button(t("common.cancel"), on_click=dialog.close).props("flat")
                ui.button(
                    t("common.save"), icon="check", on_click=_save
                ).props("color=primary")

    dialog.open()


__all__ = ["DEFAULT_WIDGETS", "register"]
