# SPDX-License-Identifier: AGPL-3.0-or-later
"""The report's answer, given the width the filter panel used to have."""

from __future__ import annotations

from typing import Any

from nicegui import ui

from kaleta.i18n import t
from kaleta.services.saved_report_service import (
    PivotResult,
    ReportResult,
    build_report_table_data,
)
from kaleta.views.components.amount_label import spaced_thousands
from kaleta.views.reports.chart_options import pivot_chart_options, report_chart_options
from kaleta.views.reports.sentence import (
    bar_widths,
    chart_title,
    dimension_label,
    result_total,
    share_percents,
)
from kaleta.views.theme import (
    BODY_MUTED,
    CARD_TITLE,
    INK,
    MONO,
    MUTED,
    PIVOT_CELL,
    PIVOT_FIGURE,
    PIVOT_FOOT,
    PIVOT_GRID,
    PIVOT_HEAD,
    PIVOT_TOTAL,
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

        # A second dimension makes the answer a matrix. The two shapes share
        # the title line and the empty state; everything under it differs.
        pivot = result if isinstance(result, PivotResult) else None
        # A column of averages does not add up to an average of anything, so on
        # that measure there is no total to draw — on the title line
        # (`KAL-RPT-004`) or in the pivot's Total column and footer.
        adds_up = str(state["metric"]) != "avg"
        column_totals = pivot.series_totals if pivot is not None else result.values

        # The title says what the chart is of, so the chart can be read
        # without looking back up at the sentence that asked for it.
        with ui.row().classes("w-full items-baseline justify-between gap-3 flex-wrap mb-5"):
            ui.label(chart_title(state)).classes(CARD_TITLE)
            total = result_total(column_totals, metric=str(state["metric"]))
            if column_totals and total is not None:
                ui.label(t("reports.result_total", amount=total)).classes(RESULT_TOTAL)

        labels = pivot.row_labels if pivot is not None else result.labels
        if not labels:
            ui.label(t("reports.no_data")).classes(f"{BODY_MUTED} text-center py-12 w-full")
            return

        if pivot is not None:
            if state["chart_type"] == "table":
                # The row header comes from the sentence and not from the
                # result: the service names its columns in English, and the
                # grid sits directly under the line that named the same
                # dimension in the reader's own language.
                _pivot_grid(pivot, row_header=dimension_label(state), show_totals=adds_up)
                return
            option = pivot_chart_options(pivot, state["chart_type"], is_dark)
            ui.echart(option).classes("w-full").style("height: 380px")
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
    widths = bar_widths(result.values)
    with ui.column().classes("w-full gap-[13px]"):
        for rank, (label, value, share, width) in enumerate(
            zip(result.labels, result.values, shares, widths, strict=False)
        ):
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


def _pivot_grid(result: PivotResult, *, row_header: str, show_totals: bool) -> None:
    """The matrix as a grid: row labels left, figures right, totals apart.

    A grid and not a ``ui.table`` because the column count is the query's, not
    the schema's, and because the figures have to wear the same tabular mono
    the bar rows do. It scrolls sideways rather than squeezing: twenty months
    of columns is a wide answer, and a wide answer squeezed is unreadable.
    """
    columns = ["minmax(148px,1.6fr)"] + ["minmax(84px,1fr)"] * len(result.series_labels)
    if show_totals:
        columns.append("minmax(96px,1fr)")

    def _figure(value: float, *, extra: str = "") -> None:
        ui.label(spaced_thousands(f"{value:,.2f}")).classes(
            f"{PIVOT_CELL} {PIVOT_FIGURE} {extra}".rstrip()
        )

    with (
        ui.element("div").classes("w-full overflow-x-auto"),
        ui.element("div").classes(PIVOT_GRID).style(f"grid-template-columns:{' '.join(columns)}"),
    ):
        ui.label(row_header).classes(PIVOT_HEAD)
        for series_label in result.series_labels:
            ui.label(series_label).classes(f"{PIVOT_HEAD} {PIVOT_FIGURE}")
        if show_totals:
            ui.label(t("reports.pivot_total")).classes(f"{PIVOT_HEAD} {PIVOT_FIGURE}")

        for row_label, cells, row_total in zip(
            result.row_labels, result.cells, result.row_totals, strict=True
        ):
            ui.label(row_label).classes(f"{PIVOT_CELL} {INK}")
            for value in cells:
                _figure(value)
            if show_totals:
                _figure(row_total, extra=PIVOT_TOTAL)

        if show_totals:
            ui.label(t("reports.pivot_total")).classes(f"{PIVOT_CELL} {PIVOT_FOOT}")
            for column_total in result.series_totals:
                _figure(column_total, extra=PIVOT_FOOT)
            _figure(sum(result.series_totals), extra=f"{PIVOT_FOOT} {PIVOT_TOTAL}")
