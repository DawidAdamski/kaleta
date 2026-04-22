"""Dashboard Command Center.

Renders a user-configurable grid of widgets. The widget catalog lives in
``dashboard_widgets.py``; the dashboard's only job is layout + the
"Customize" entry point. The ordered list of enabled widget IDs is
persisted in ``app.storage.user["dashboard_widgets"]``.
"""

from __future__ import annotations

from nicegui import app, ui

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


def register() -> None:
    @ui.page("/")
    async def dashboard() -> None:
        is_dark: bool = app.storage.user.get("dark_mode", False)
        order = resolve_user_widgets(app.storage.user.get("dashboard_widgets"))

        with page_layout(t("dashboard.title")):
            with ui.row().classes("w-full items-center justify-between mb-2"):
                ui.label(t("dashboard.title")).classes(PAGE_TITLE)
                ui.button(
                    t("dashboard_widgets.customize"),
                    icon="tune",
                    on_click=lambda: _open_customize_dialog(order),
                ).props("flat color=primary")

            async with AsyncSessionFactory() as session:
                kpis = [WIDGETS[w] for w in order if WIDGETS[w].size == "kpi"]
                halves = [WIDGETS[w] for w in order if WIDGETS[w].size == "half"]
                fulls = [WIDGETS[w] for w in order if WIDGETS[w].size == "full"]

                if kpis:
                    with ui.row().classes("w-full gap-4 flex-wrap"):
                        for w in kpis:
                            await w.render(session, is_dark)

                if halves:
                    with ui.grid(columns=2).classes("w-full gap-4 md:grid-cols-2"):
                        for w in halves:
                            await w.render(session, is_dark)

                for w in fulls:
                    await w.render(session, is_dark)


def _open_customize_dialog(current_order: list[str]) -> None:
    """Dialog for enabling, disabling, and reordering dashboard widgets."""
    # Working list (ordered) we mutate as the user interacts.
    order: list[str] = list(current_order)
    # Widgets not currently in the order are "disabled" — list them after.
    disabled = [wid for wid in WIDGETS if wid not in order]
    working = order + disabled  # render every widget, tick enabled ones
    enabled: dict[str, bool] = {wid: (wid in order) for wid in working}

    with ui.dialog() as dialog, ui.card().classes("min-w-96 max-w-xl"):
        ui.label(t("dashboard_widgets.customize_title")).classes(
            "text-lg font-semibold"
        )
        ui.label(t("dashboard_widgets.customize_hint")).classes(
            "text-xs text-grey-6 mb-2"
        )

        list_container = ui.column().classes("w-full gap-1 max-h-96 overflow-y-auto")

        def _swap(i: int, j: int) -> None:
            if 0 <= i < len(working) and 0 <= j < len(working):
                working[i], working[j] = working[j], working[i]
                _render_list()

        def _toggle(widget_id: str, value: bool) -> None:
            enabled[widget_id] = value

        def _render_list() -> None:
            list_container.clear()
            with list_container:
                for i, wid in enumerate(working):
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
                        ui.button(icon="arrow_upward").props(
                            "flat dense round size=sm"
                        ).on_click(lambda _, _i=i: _swap(_i, _i - 1))
                        ui.button(icon="arrow_downward").props(
                            "flat dense round size=sm"
                        ).on_click(lambda _, _i=i: _swap(_i, _i + 1))

        _render_list()

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
