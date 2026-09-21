# SPDX-License-Identifier: AGPL-3.0-or-later
"""The report's answer, given the width the filter panel used to have."""

from __future__ import annotations

from typing import Any

from nicegui import ui

from kaleta.i18n import t
from kaleta.services.saved_report_service import ReportResult, build_report_table_data
from kaleta.views.components.amount_label import spaced_thousands
from kaleta.views.reports.chart_options import report_chart_options
from kaleta.views.reports.sentence import chart_title, result_total, share_percents
from kaleta.views.theme import (
    BODY_MUTED,
    CARD_TITLE,
    INK,
    MONO,
    MUTED,
    REPORT_BAR_FILL,
    REPORT_BAR_ROW,
    REPORT_BAR_TRACK,
    RESULT_TOTAL,
    TABLE_SURFACE,
    bar_ramp,
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
        with ui.row().classes("w-full items-baseline justify-between gap-3 flex-wrap mb-5"):
            ui.label(chart_title(state)).classes(CARD_TITLE)
            total = result_total(result.values, metric=str(state["metric"]))
            if result.values and total is not None:
                ui.label(t("reports.result_total", amount=total)).classes(RESULT_TOTAL)

        if not result.labels:
            ui.label(t("reports.no_data")).classes(f"{BODY_MUTED} text-center py-12 w-full")
            return

        if state["chart_type"] == "bar":
            _bar_rows(result)
            return

        if state["chart_type"] == "table":
            table_data = build_report_table_data(result)
            ui.table(columns=table_data.columns, rows=table_data.rows).classes(
                f"{TABLE_SURFACE} mt-2"
            ).props("flat dense")
            return

        option = report_chart_options(result, state["chart_type"], is_dark)
        ui.echart(option).classes("w-full").style("height: 380px")

    return chart_zone


def _bar_rows(result: ReportResult) -> None:
    """The ranking as rows, the way artboard `3e` draws it.

    A chart library was drawing ten labelled bars inside a canvas that could
    not be selected, searched or read by a screen reader, and whose type was
    never the app's own. These are four columns of text and one div: name,
    track, value, share — ranked, and shaded darkest first so the order
    survives without a legend.
    """
    shares = share_percents(result.values)
    widest = max((abs(v) for v in result.values), default=0.0)
    with ui.column().classes("w-full gap-[13px]"):
        for rank, (label, value, share) in enumerate(
            zip(result.labels, result.values, shares, strict=False)
        ):
            width = abs(value) / widest * 100 if widest else 0.0
            with ui.element("div").classes(f"{REPORT_BAR_ROW} w-full"):
                ui.label(label).classes(f"{INK} text-[13px] truncate")
                with ui.element("span").classes(REPORT_BAR_TRACK):
                    ui.element("span").classes(REPORT_BAR_FILL).style(
                        f"width:{width:.2f}%;background:{bar_ramp(rank, len(result.labels))}"
                    )
                ui.label(spaced_thousands(f"{value:,.2f}")).classes(
                    f"{MONO} {INK} text-[13px] font-medium text-right"
                )
                ui.label(f"{share:.0f}%").classes(f"{MONO} {MUTED} text-[12px] text-right")
