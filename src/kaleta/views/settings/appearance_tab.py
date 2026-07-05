# SPDX-License-Identifier: AGPL-3.0-or-later
"""Settings — Appearance tab (theme, sidebar)."""

from __future__ import annotations

from nicegui import app, ui

from kaleta.i18n import t
from kaleta.views.settings.helpers import set_user_key


def render_appearance_tab() -> None:
    with ui.row().classes("w-full gap-6 flex-wrap items-start"):
        with ui.card().classes("p-6 min-w-72 w-80"):
            with ui.row().classes("items-center gap-2 mb-4"):
                ui.icon("dark_mode", color="primary").classes("text-xl")
                ui.label(t("settings.theme")).classes("text-lg font-semibold")

            is_dark = bool(app.storage.user.get("dark_mode", False))

            def _set_theme(dark: bool) -> None:
                app.storage.user["dark_mode"] = dark
                ui.dark_mode(dark)
                ui.navigate.reload()

            ui.toggle(
                {False: t("settings.theme_light"), True: t("settings.theme_dark")},
                value=is_dark,
                on_change=lambda e: _set_theme(bool(e.value)),
            ).classes("w-full")
            ui.label(t("settings.theme_hint")).classes("text-xs text-slate-500 mt-2")

        with ui.card().classes("p-6 min-w-72 w-80"):
            with ui.row().classes("items-center gap-2 mb-4"):
                ui.icon("menu", color="primary").classes("text-xl")
                ui.label(t("settings.sidebar")).classes("text-lg font-semibold")

            is_mini = bool(app.storage.user.get("sidebar_mini", False))
            ui.toggle(
                {
                    False: t("settings.sidebar_expanded"),
                    True: t("settings.sidebar_collapsed"),
                },
                value=is_mini,
                on_change=lambda e: set_user_key("sidebar_mini", bool(e.value)),
            ).classes("w-full")
            ui.label(t("settings.sidebar_hint")).classes("text-xs text-slate-500 mt-2")
