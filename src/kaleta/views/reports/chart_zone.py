# SPDX-License-Identifier: AGPL-3.0-or-later
"""The report's answer, given the width the filter panel used to have."""

from __future__ import annotations

from typing import Any

from nicegui import ui

from kaleta.i18n import t
from kaleta.services.saved_report_service import build_report_table_data
from kaleta.views.reports.chart_options import report_chart_options
from kaleta.views.reports.sentence import chart_title
from kaleta.views.theme import (
    AMOUNT_NEUTRAL,
    BODY_MUTED,
    MONO,
    MUTED,
    SECTION_HEADING,
    TABLE_SURFACE,
)


def build_chart_zone(state: dict[str, Any], *, is_dark: bool) -> Any:
    @ui.refreshable
    def chart_zone() -> None:
        if state["running"]:
            with ui.row().classes("items-center gap-2 h-80 justify-center w-full"):
                ui.spinner(size="lg")
                ui.label(t("common.loading")).classes(BODY_MUTED)
            return
        if state["error"]:
            with ui.row().classes("items-center gap-2 w-full"):
                ui.icon("error_outline", size="1.1rem").classes("k-trend--neg")
                ui.label(state["error"]).classes("k-trend--neg text-sm")
            return

        result = state["result"]
        if result is None:
            with (
                ui.column().classes("h-80 w-full items-center justify-center gap-2"),
            ):
                ui.icon("query_stats", size="2.2rem").classes(MUTED)
                ui.label(t("reports.run_to_preview")).classes(BODY_MUTED)
            return

        # The title says what the chart is of, so the chart can be read
        # without looking back up at the sentence that asked for it.
        with ui.row().classes("w-full items-baseline justify-between gap-3 flex-wrap"):
            ui.label(chart_title(state)).classes(SECTION_HEADING)
            if result.values:
                total = sum(result.values)
                ui.label(f"{total:,.2f}").classes(f"{AMOUNT_NEUTRAL} {MONO} text-sm")

        if not result.labels:
            ui.label(t("reports.no_data")).classes(f"{BODY_MUTED} text-center py-12 w-full")
            return

        if state["chart_type"] == "table":
            table_data = build_report_table_data(result)
            ui.table(columns=table_data.columns, rows=table_data.rows).classes(
                f"{TABLE_SURFACE} mt-2"
            ).props("flat dense")
            return

        option = report_chart_options(result, state["chart_type"], is_dark)
        # Horizontal bars need room per bar; the other types do not grow.
        height = max(280, 34 * len(result.labels)) if state["chart_type"] == "bar" else 380
        ui.echart(option).classes("w-full").style(f"height: {height}px")

    return chart_zone
