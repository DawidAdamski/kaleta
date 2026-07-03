"""Settings — About tab."""

from __future__ import annotations

from nicegui import ui

from kaleta.config.settings import settings as app_settings
from kaleta.i18n import t
from kaleta.views.settings.helpers import about_row


def render_about_tab() -> None:
    with ui.card().classes("p-6 w-full"):
        with ui.row().classes("items-center gap-2 mb-4"):
            ui.icon("info", color="primary").classes("text-xl")
            ui.label(t("settings.about_title")).classes("text-lg font-semibold")

        with ui.column().classes("gap-1"):
            about_row(t("settings.about_mode"), app_settings.mode)
            about_row(t("settings.about_debug"), "yes" if app_settings.debug else "no")
            about_row(t("settings.about_host"), app_settings.host)
            about_row(t("settings.about_port"), str(app_settings.port))

        ui.separator().classes("my-4")

        with ui.row().classes("gap-3 flex-wrap"):
            ui.button(
                t("settings.about_github"),
                icon="code",
                on_click=lambda: ui.navigate.to(
                    "https://github.com/DawidAdamski/kaleta", new_tab=True
                ),
            ).props("outline color=primary")
            ui.button(
                t("settings.about_docs"),
                icon="menu_book",
                on_click=lambda: ui.navigate.to("/docs", new_tab=True),
            ).props("outline color=primary")
