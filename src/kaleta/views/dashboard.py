"""Dashboard Command Center.

Renders a user-configurable grid of widgets. The widget catalog lives in
``dashboard_widgets.py``; the dashboard's only job is layout + the
"Edit layout" / "Customize" entry points. The ordered list of enabled
widget IDs is persisted in ``app.storage.user["dashboard_widgets"]``.

Reordering happens via drag-and-drop (SortableJS) inside an Edit mode
toggle. Each widget card carries a ``data-widget-id`` and ``data-size``
attribute so the client can pull the new order from the DOM and POST it
back to the server.
"""

from __future__ import annotations

from nicegui import app, ui
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.db import AsyncSessionFactory
from kaleta.i18n import t
from kaleta.views.dashboard_widgets import (
    DEFAULT_WIDGETS,
    WIDGETS,
    Widget,
    resolve_user_widgets,
)
from kaleta.views.layout import page_layout
from kaleta.views.theme import PAGE_TITLE

_SORTABLE_SCRIPT = '<script src="/static/vendor/sortable.min.js"></script>'

_EDIT_MODE_STYLE = """
<style>
  .dash-widget-wrap { position: relative; }
  /* Decorative drag icon in the top-right corner. Hidden outside edit
     mode. Does not itself receive pointer events — the whole card is
     the drag surface, and SortableJS listens on the card container. */
  .dash-widget-wrap .dash-drag-handle-icon {
    position: absolute; top: 6px; right: 6px; z-index: 5;
    display: none;
    padding: 2px 4px;
    border-radius: 6px;
    color: #64748b;
    background: rgba(148,163,184,0.14);
    pointer-events: none;
  }
  body.dash-editing .dash-widget-wrap {
    outline: 1px dashed rgba(100,116,139,0.45);
    outline-offset: 4px;
    border-radius: 10px;
    cursor: grab;
  }
  body.dash-editing .dash-widget-wrap:active { cursor: grabbing; }
  body.dash-editing .dash-widget-wrap .dash-drag-handle-icon {
    display: block;
  }
  body.dash-editing .dash-widget-wrap:focus-visible {
    outline: 2px solid rgb(59,130,246);
  }
  .dash-edit-banner { display: none; }
  body.dash-editing .dash-edit-banner { display: flex; }
  .sortable-ghost { opacity: 0.3; }
  .sortable-chosen { cursor: grabbing; }
</style>
"""

_INIT_JS = """
<script>
window.__kaletaInitDashSortable = function() {
  const groups = ['kpi', 'half', 'full'];
  if (typeof Sortable === 'undefined') {
    // SortableJS script hasn't loaded yet; retry once it does.
    console.warn('[dashboard] Sortable not ready, retrying in 150ms');
    setTimeout(window.__kaletaInitDashSortable, 150);
    return;
  }
  groups.forEach(size => {
    const container = document.getElementById('dash-' + size);
    if (!container) return;
    if (container.__sortable) {
      container.__sortable.destroy();
      container.__sortable = null;
    }
    if (!document.body.classList.contains('dash-editing')) return;
    container.__sortable = new Sortable(container, {
      draggable: '.dash-widget-wrap',
      animation: 150,
      group: 'dash-' + size,
      ghostClass: 'sortable-ghost',
      chosenClass: 'sortable-chosen',
      onEnd: () => window.__kaletaPostDashOrder(),
    });
  });
  console.debug('[dashboard] Sortable initialised, editing =',
    document.body.classList.contains('dash-editing'));
};
window.__kaletaPostDashOrder = function() {
  const collect = size => Array.from(
    document.querySelectorAll('#dash-' + size + ' [data-widget-id]')
  ).map(e => e.dataset.widgetId);
  const payload = {kpi: collect('kpi'), half: collect('half'), full: collect('full')};
  fetch('/_dashboard/order', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
  }).catch(err => console.warn('[dashboard] POST order failed', err));
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
  window.__kaletaPostDashOrder();
};
document.addEventListener('keydown', window.__kaletaDashKbdMove);
</script>
"""


def _merge_order(
    payload: dict[str, list[str]], stored: list[str]
) -> list[str]:
    """Flatten per-size groups into a single ordered list.

    Only widget IDs that (a) exist in WIDGETS and (b) were already enabled
    (i.e. present in ``stored``) and (c) have a size matching the group
    they're posted under are kept. Falls back to ``stored`` if the merge
    would produce an empty result.
    """
    stored_set = set(stored)
    merged: list[str] = []
    for size in ("kpi", "half", "full"):
        for wid in payload.get(size, []):
            if not isinstance(wid, str):
                continue
            w = WIDGETS.get(wid)
            if w is None or w.size != size:
                continue
            if wid in stored_set and wid not in merged:
                merged.append(wid)
    return merged or list(stored)


class _OrderPayload(BaseModel):
    kpi: list[str] = []
    half: list[str] = []
    full: list[str] = []


def _register_order_endpoint() -> None:
    from nicegui import app as nicegui_app

    @nicegui_app.post("/_dashboard/order", include_in_schema=False)
    async def _save_order(payload: _OrderPayload) -> dict[str, str]:
        stored = resolve_user_widgets(app.storage.user.get("dashboard_widgets"))
        app.storage.user["dashboard_widgets"] = _merge_order(
            payload.model_dump(), stored
        )
        return {"status": "ok"}


def register() -> None:
    _register_order_endpoint()

    @ui.page("/")
    async def dashboard() -> None:
        is_dark: bool = app.storage.user.get("dark_mode", False)
        order = resolve_user_widgets(app.storage.user.get("dashboard_widgets"))

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
                        on_click=lambda: _open_customize_dialog(order),
                    ).props("flat color=primary")

            with ui.row().classes(
                "dash-edit-banner w-full items-center gap-2 p-3 mb-3 rounded "
                "bg-amber-100 dark:bg-amber-900/40 "
                "text-amber-900 dark:text-amber-100 text-sm"
            ):
                ui.icon("info")
                ui.label(t("dashboard_widgets.edit_banner"))

            async with AsyncSessionFactory() as session:
                kpis = [WIDGETS[w] for w in order if WIDGETS[w].size == "kpi"]
                halves = [WIDGETS[w] for w in order if WIDGETS[w].size == "half"]
                fulls = [WIDGETS[w] for w in order if WIDGETS[w].size == "full"]

                with ui.row().props('id="dash-kpi"').classes(
                    "w-full gap-4 flex-wrap"
                ):
                    for w in kpis:
                        await _render_wrapped(w, session, is_dark)
                    if not kpis:
                        _render_empty_placeholder("kpi")

                with ui.grid(columns=2).props('id="dash-half"').classes(
                    "w-full gap-4 md:grid-cols-2"
                ):
                    for w in halves:
                        await _render_wrapped(w, session, is_dark)
                    if not halves:
                        _render_empty_placeholder("half")

                with ui.column().props('id="dash-full"').classes(
                    "w-full gap-4"
                ):
                    for w in fulls:
                        await _render_wrapped(w, session, is_dark)
                    if not fulls:
                        _render_empty_placeholder("full")

            ui.run_javascript(
                "window.__kaletaInitDashSortable && window.__kaletaInitDashSortable()"
            )


async def _render_wrapped(
    widget: Widget, session: AsyncSession, is_dark: bool
) -> None:
    with ui.element("div").props(
        f'data-widget-id="{widget.id}" data-size="{widget.size}" tabindex="0"'
    ).classes("dash-widget-wrap"):
        with ui.element("div").classes("dash-drag-handle-icon").props(
            f'title="{t("dashboard_widgets.drag_hint")}"'
        ):
            ui.icon("drag_indicator")
        await widget.render(session, is_dark)


def _render_empty_placeholder(size: str) -> None:
    with ui.element("div").classes(
        "dash-edit-banner w-full p-4 text-center text-sm "
        "text-slate-500 border border-dashed border-slate-300 rounded"
    ):
        ui.label(t("dashboard_widgets.empty_size_group"))
    _ = size


def _open_customize_dialog(current_order: list[str]) -> None:
    """Dialog for enabling and disabling dashboard widgets.

    Reordering happens via Edit mode on the dashboard itself; this dialog
    only manages which widgets are shown.
    """
    order: list[str] = list(current_order)
    disabled = [wid for wid in WIDGETS if wid not in order]
    working = order + disabled
    enabled: dict[str, bool] = {wid: (wid in order) for wid in working}

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
                    ui.badge(w.size).props("color=grey-6").classes("text-xs")

        def _save() -> None:
            final = [wid for wid in working if enabled.get(wid)]
            if not final:
                ui.notify(t("dashboard_widgets.min_one"), color="negative")
                return
            app.storage.user["dashboard_widgets"] = final
            ui.notify(t("dashboard_widgets.saved"), color="positive")
            dialog.close()
            ui.navigate.to("/")

        def _reset() -> None:
            app.storage.user["dashboard_widgets"] = list(DEFAULT_WIDGETS)
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
