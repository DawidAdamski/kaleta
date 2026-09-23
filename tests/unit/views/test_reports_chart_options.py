# SPDX-License-Identifier: AGPL-3.0-or-later
"""The report chart's options (artboard 3e).

These moved out of ``saved_report_service`` — a chart option dict is
presentation, not business logic, and on the service side it had never met
the app palette. Presentational; no BDD scenario claims it.
"""

from __future__ import annotations

from kaleta.services.saved_report_service import PivotResult, ReportResult
from kaleta.views.chart_utils import chart_palette
from kaleta.views.reports.chart_options import pivot_chart_options, report_chart_options
from kaleta.views.theme import BAR_RAMP_STEPS, bar_ramp


def _result(labels: list[str] | None = None, values: list[float] | None = None) -> ReportResult:
    return ReportResult(
        labels=labels if labels is not None else ["Food", "Rent", "Fun"],
        values=values if values is not None else [300.0, 500.0, 200.0],
        column_header="Category",
        metric_header="Total Amount",
    )


class TestBarRamp:
    """The bar result is rows of HTML now, so what used to be an ECharts
    option is a ramp step per rank (`KAL-RPT-002`). The rows themselves are
    covered end to end; this is the arithmetic behind their colour."""

    def test_the_first_row_takes_the_darkest_step(self) -> None:
        assert bar_ramp(0, 10) == "var(--k-ramp-1)"

    def test_the_last_row_takes_the_lightest(self) -> None:
        assert bar_ramp(9, 10) == f"var(--k-ramp-{BAR_RAMP_STEPS})"

    def test_the_ramp_never_runs_past_its_last_step(self) -> None:
        # Twenty rows share six greens; a 21st step would be a variable that
        # does not exist, and the bar would come out unpainted.
        assert all(
            bar_ramp(rank, 20) in {f"var(--k-ramp-{n})" for n in range(1, BAR_RAMP_STEPS + 1)}
            for rank in range(20)
        )

    def test_it_never_goes_backwards(self) -> None:
        steps = [int(bar_ramp(rank, 13).split("-")[-1].rstrip(")")) for rank in range(13)]
        assert steps == sorted(steps)

    def test_a_single_row_is_not_divided_by_zero(self) -> None:
        assert bar_ramp(0, 1) == "var(--k-ramp-1)"

    def test_the_bar_type_is_not_answered_here_any_more(self) -> None:
        # `report_chart_options` only ever answers for the three types that
        # really are charts; `bar` is rows and `table` is a table.
        assert report_chart_options(_result(), "bar", is_dark=False)["series"][0]["type"] == "line"


class TestOtherTypes:
    def test_a_pie_names_every_slice(self) -> None:
        options = report_chart_options(_result(), "pie", is_dark=False)
        data = options["series"][0]["data"]
        assert [d["name"] for d in data] == ["Food", "Rent", "Fun"]

    def test_a_donut_is_a_pie_with_a_hole(self) -> None:
        pie = report_chart_options(_result(), "pie", is_dark=False)
        donut = report_chart_options(_result(), "donut", is_dark=False)
        assert isinstance(donut["series"][0]["radius"], list)
        assert not isinstance(pie["series"][0]["radius"], list)

    def test_a_line_keeps_the_order_it_was_given(self) -> None:
        # A line over months must not be reversed the way the bars are.
        options = report_chart_options(_result(), "line", is_dark=False)
        assert options["xAxis"]["data"] == ["Food", "Rent", "Fun"]
        assert options["series"][0]["data"] == [300.0, 500.0, 200.0]

    def test_every_type_gets_the_palette_seeded(self) -> None:
        for chart_type in ("line", "pie", "donut"):
            options = report_chart_options(_result(), chart_type, is_dark=False)
            assert options["color"] == chart_palette(False)


def _pivot() -> PivotResult:
    """Two categories over two months — the smallest matrix with a hole in it."""
    return PivotResult(
        row_header="Category",
        series_header="Month",
        row_labels=["Food", "Fun"],
        series_labels=["2025-01", "2025-02"],
        cells=[[100.0, 50.0], [0.0, 30.0]],
        metric_header="Total Amount",
        row_totals=[150.0, 30.0],
        series_totals=[100.0, 80.0],
    )


class TestPivotCharts:
    """A second dimension is a matrix, and a matrix has two readings: what
    each row is made of (stacked bars) and how each row moves (lines). The
    grid itself is drawn in HTML; these are the two that really are charts."""

    def test_a_stacked_bar_puts_the_rows_on_the_axis(self) -> None:
        options = pivot_chart_options(_pivot(), "bar", is_dark=False)
        assert options["xAxis"]["data"] == ["Food", "Fun"]

    def test_every_segment_shares_one_stack(self) -> None:
        options = pivot_chart_options(_pivot(), "bar", is_dark=False)
        assert [s["type"] for s in options["series"]] == ["bar", "bar"]
        assert {s["stack"] for s in options["series"]} == {"total"}

    def test_a_series_per_month_reads_down_its_own_column(self) -> None:
        # Series 0 is January: 100 for Food, nothing for Fun. A segment built
        # across the row instead would stack Food's two months on one bar.
        options = pivot_chart_options(_pivot(), "bar", is_dark=False)
        assert options["series"][0]["data"] == [100.0, 0.0]
        assert options["series"][1]["data"] == [50.0, 30.0]

    def test_the_legend_names_the_series_values(self) -> None:
        options = pivot_chart_options(_pivot(), "bar", is_dark=False)
        assert [s["name"] for s in options["series"]] == ["2025-01", "2025-02"]
        # Drawn, and not the scrolling kind: twelve months should wrap onto a
        # second line rather than hide behind a pair of arrows.
        assert options["legend"].get("type") != "scroll"

    def test_a_line_runs_along_the_series_axis_one_per_row(self) -> None:
        options = pivot_chart_options(_pivot(), "line", is_dark=False)
        assert options["xAxis"]["data"] == ["2025-01", "2025-02"]
        assert [s["name"] for s in options["series"]] == ["Food", "Fun"]
        assert options["series"][0]["data"] == [100.0, 50.0]

    def test_both_shapes_get_the_palette_seeded(self) -> None:
        for chart_type in ("bar", "line"):
            options = pivot_chart_options(_pivot(), chart_type, is_dark=False)
            assert options["color"] == chart_palette(False)
