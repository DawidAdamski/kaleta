# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reports library landing page."""

from __future__ import annotations

from nicegui import ui

from kaleta.i18n import t
from kaleta.views.layout import page_layout
from kaleta.views.reports_canned.catalog import REPORTS
from kaleta.views.theme import PAGE_TITLE


def register() -> None:
    @ui.page("/reports")
    async def reports_landing() -> None:
        with page_layout(t("reports_lib.title")):
            ui.label(t("reports_lib.title")).classes(PAGE_TITLE)
            ui.label(t("reports_lib.intro")).classes("text-sm text-grey-6 -mt-2 mb-4")

            with ui.row().classes("w-full gap-4 flex-wrap"):
                for slug, title_key, desc_key, icon, colour in REPORTS:
                    with ui.card().classes(
                        "p-4 flex-1 min-w-64 max-w-80 cursor-pointer hover:shadow-lg"
                    ) as card:
                        with ui.row().classes("items-start gap-3 w-full no-wrap"):
                            ui.icon(icon, color=colour).classes("text-3xl")
                            with ui.column().classes("gap-1 flex-1 min-w-0"):
                                ui.label(t(title_key)).classes("text-base font-semibold")
                                ui.label(t(desc_key)).classes("text-xs text-grey-6 leading-snug")
                        card.on(
                            "click",
                            lambda s=slug: ui.navigate.to(f"/reports/{s}"),
                        )

            ui.separator().classes("my-4")
            with ui.row().classes("items-center gap-2"):
                ui.icon("build", color="grey-6")
                ui.label(t("reports_lib.advanced_builder_hint")).classes("text-sm text-grey-6")
                ui.button(
                    t("reports_lib.open_builder"),
                    icon="open_in_new",
                    on_click=lambda: ui.navigate.to("/reports/builder"),
                ).props("flat color=primary")
