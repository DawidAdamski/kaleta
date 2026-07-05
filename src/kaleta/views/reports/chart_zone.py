# SPDX-License-Identifier: AGPL-3.0-or-later
"""Report builder chart preview zone."""

from __future__ import annotations

from typing import Any

from nicegui import ui

from kaleta.i18n import t
from kaleta.services.saved_report_service import build_echart_option, build_report_table_data
from kaleta.views.theme import TABLE_SURFACE


def build_chart_zone(state: dict[str, Any], *, is_dark: bool) -> Any:
    @ui.refreshable
    def chart_zone() -> None:
        if state["running"]:
            with ui.row().classes("items-center gap-2 h-64 justify-center w-full"):
                ui.spinner(size="xl")
                ui.label(t("common.loading"))
            return
        if state["error"]:
            ui.label(f"Error: {state['error']}").classes("text-negative")
            return
        result = state["result"]
        if result is None:
            with (
                ui.element("div").classes(
                    "h-64 flex items-center justify-center text-slate-400 "
                    "border-2 border-dashed rounded-lg w-full"
                ),
                ui.column().classes("items-center gap-2"),
            ):
                ui.icon("bar_chart").classes("text-5xl")
                ui.label(t("reports.run_to_preview"))
            return
        if not result.labels:
            ui.label(t("reports.no_data")).classes("text-slate-400 text-center py-8 w-full")
            return

        chart_type = state["chart_type"]
        if chart_type == "table":
            table_data = build_report_table_data(result)
            ui.table(columns=table_data.columns, rows=table_data.rows).classes(TABLE_SURFACE).props(
                "flat dense"
            )
        else:
            option = build_echart_option(result, chart_type, is_dark)
            ui.echart(option).classes("w-full").style("height: 380px")

    return chart_zone
