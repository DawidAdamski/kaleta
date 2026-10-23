# SPDX-License-Identifier: AGPL-3.0-or-later
"""The report's answer, given the width the filter panel used to have."""

from __future__ import annotations

import dataclasses
from typing import Any

from nicegui import ui

from kaleta.i18n import t
from kaleta.services.saved_report_service import (
    NO_INSTITUTION_LABEL,
    OTHER_ROW_LABEL,
    TYPE_LABEL_PREFIX,
    UNCATEGORISED_LABEL,
    WEEKDAY_LABEL_PREFIX,
    PivotResult,
    ReportResult,
    build_report_table_data,
)
from kaleta.views.components.amount_label import spaced_thousands
from kaleta.views.reports.chart_options import pivot_chart_options, report_chart_options
from kaleta.views.reports.sentence import (
    bar_widths,
    chart_title,
    derived_headers,
    derived_texts,
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
    PIVOT_DERIVED,
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

#: Postgres ``dow`` is 0 = Sunday. Reuse the payment calendar's day names
#: rather than shipping a second copy of Monday…Sunday.
_WEEKDAY_KEYS = ("sun", "mon", "tue", "wed", "thu", "fri", "sat")


def _resolve_label(raw: str) -> str:
    """One axis label as the reader sees it; a plain value passes through.

    User-entered names (a category, an account) and period strings
    (``2025-01``) are already their own display text. Only the service's
    sentinels — a weekday ordinal, a type's enum value, the
    Uncategorised / No-Institution / Other buckets — are translated here.
    """
    if raw == UNCATEGORISED_LABEL:
        return t("reports.uncategorised")
    if raw == NO_INSTITUTION_LABEL:
        return t("reports.no_institution")
    if raw == OTHER_ROW_LABEL:
        return t("reports.other_row")
    if raw.startswith(WEEKDAY_LABEL_PREFIX):
        dow = int(raw[len(WEEKDAY_LABEL_PREFIX) :])
        return t(f"payment_calendar.wd_full_{_WEEKDAY_KEYS[dow]}")
    if raw.startswith(TYPE_LABEL_PREFIX):
        return t(f"reports.type_{raw[len(TYPE_LABEL_PREFIX) :]}")
    return raw


def _localize(result: ReportResult | PivotResult) -> ReportResult | PivotResult:
    """A copy of the service's answer with every key and sentinel resolved.

    The service stays presentation-free: it labels its axes with i18n keys
    (``dim_category``, ``metric_sum``) and its rows with sentinels for the
    buckets no language spells the same. This is the one place ``t()`` turns
    them into the reader's own words, so the chart, the grid and the table
    below all draw from an already-localized result.
    """
    if isinstance(result, PivotResult):
        return dataclasses.replace(
            result,
            row_header=t(f"reports.{result.row_header}"),
            series_header=t(f"reports.{result.series_header}"),
            metric_header=t(f"reports.{result.metric_header}"),
            row_labels=[_resolve_label(label) for label in result.row_labels],
            series_labels=[_resolve_label(label) for label in result.series_labels],
        )
    return dataclasses.replace(
        result,
        column_header=t(f"reports.{result.column_header}"),
        metric_header=t(f"reports.{result.metric_header}"),
        labels=[_resolve_label(label) for label in result.labels],
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

        # The service names its axes with i18n keys and its rows with
        # sentinels; this is the one place they become the reader's own words.
        result = _localize(result)

        # A second dimension makes the answer a matrix. The two shapes share
        # the title line and the empty state; everything under it differs.
        # A column of averages does not add up to an average of anything, so on
        # that measure there is no total to draw — on the title line
        # (`KAL-RPT-004`) or in the pivot's Total column and footer.
        adds_up = str(state["metric"]) != "avg"
        column_totals = result.series_totals if isinstance(result, PivotResult) else result.values
        labels = result.row_labels if isinstance(result, PivotResult) else result.labels

        # The title says what the chart is of, so the chart can be read
        # without looking back up at the sentence that asked for it.
        with ui.row().classes("w-full items-baseline justify-between gap-3 flex-wrap mb-5"):
            ui.label(chart_title(state)).classes(CARD_TITLE)
            total = result_total(column_totals, metric=str(state["metric"]))
            if column_totals and total is not None:
                ui.label(t("reports.result_total", amount=total)).classes(RESULT_TOTAL)

        if not labels:
            ui.label(t("reports.no_data")).classes(f"{BODY_MUTED} text-center py-12 w-full")
            return

        if isinstance(result, PivotResult):
            if state["chart_type"] == "table":
                # The row header is the localized dimension key the result
                # already carries, so the grid's corner names the same
                # dimension the sentence above it does, in the reader's
                # language, and stays tied to the data the last run produced.
                _pivot_grid(result, row_header=result.row_header, show_totals=adds_up)
                return
            option = pivot_chart_options(result, state["chart_type"], is_dark)
            ui.echart(option).classes("w-full").style("height: 380px")
            return

        # One-dimensional from here: ``result`` is a ``ReportResult``.
        if state["chart_type"] == "bar":
            _bar_rows(result)
            return

        if state["chart_type"] == "table":
            _result_table(result)
            return

        option = report_chart_options(result, state["chart_type"], is_dark)
        ui.echart(option).classes("w-full").style("height: 380px")

    return chart_zone


def _result_table(result: ReportResult) -> None:
    """The one-dimensional table, with the derived columns after the value."""
    table_data = build_report_table_data(result)
    columns, rows = list(table_data.columns), [dict(row) for row in table_data.rows]
    derived = result.derived
    if derived is not None:
        headers = derived_headers(derived.columns, derived.window)
        for position, header in enumerate(headers):
            columns.append(
                {"name": f"d{position}", "label": header, "field": f"d{position}", "align": "right"}
            )
        line = derived.lines[0]
        for index, row in enumerate(rows):
            for position, text in enumerate(derived_texts(line, index, derived.columns)):
                row[f"d{position}"] = text
    ui.table(columns=columns, rows=rows).classes(f"{TABLE_SURFACE} mt-2").props("flat dense")


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
    derived = result.derived
    headers = derived_headers(derived.columns, derived.window) if derived is not None else []
    per_series = ["minmax(84px,1fr)"] + ["minmax(64px,0.8fr)"] * len(headers)
    columns = ["minmax(148px,1.6fr)"] + per_series * len(result.series_labels)
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
            # Each derived column sits beside the series cell it was derived
            # from, so a month's change reads next to the month.
            for header in headers:
                ui.label(header).classes(f"{PIVOT_HEAD} {PIVOT_FIGURE} {PIVOT_DERIVED}")
        if show_totals:
            ui.label(t("reports.pivot_total")).classes(f"{PIVOT_HEAD} {PIVOT_FIGURE}")

        for row_index, (row_label, cells, row_total) in enumerate(
            zip(result.row_labels, result.cells, result.row_totals, strict=True)
        ):
            ui.label(row_label).classes(f"{PIVOT_CELL} {INK}")
            for series_index, value in enumerate(cells):
                _figure(value)
                if derived is not None:
                    line = derived.lines[row_index]
                    for text in derived_texts(line, series_index, derived.columns):
                        ui.label(text).classes(
                            f"{PIVOT_CELL} {PIVOT_FIGURE} {PIVOT_DERIVED} {MUTED}"
                        )
            if show_totals:
                _figure(row_total, extra=PIVOT_TOTAL)

        if show_totals:
            ui.label(t("reports.pivot_total")).classes(f"{PIVOT_CELL} {PIVOT_FOOT}")
            for column_total in result.series_totals:
                _figure(column_total, extra=PIVOT_FOOT)
                # A derived figure of the column total is not asked for;
                # the footer keeps its grid by leaving those cells empty.
                for _header in headers:
                    ui.label("").classes(f"{PIVOT_CELL} {PIVOT_FOOT}")
            _figure(sum(result.series_totals), extra=f"{PIVOT_FOOT} {PIVOT_TOTAL}")
