# SPDX-License-Identifier: AGPL-3.0-or-later
"""The report chart's options (artboard 3e).

These moved out of ``saved_report_service`` — a chart option dict is
presentation, not business logic, and on the service side it had never met
the app palette. Presentational; no BDD scenario claims it.
"""

from __future__ import annotations

from kaleta.services.saved_report_service import ReportResult
from kaleta.views.chart_utils import chart_palette
from kaleta.views.reports.chart_options import report_chart_options


def _result(labels: list[str] | None = None, values: list[float] | None = None) -> ReportResult:
    return ReportResult(
        labels=labels if labels is not None else ["Food", "Rent", "Fun"],
        values=values if values is not None else [300.0, 500.0, 200.0],
        column_header="Category",
        metric_header="Total Amount",
    )


class TestBarOptions:
    def test_the_bars_run_left_to_right(self) -> None:
        # Vertical bars had to rotate the category names 30° past six items,
        # and a rotated name is slower to read than the number beside it.
        options = report_chart_options(_result(), "bar", is_dark=False)
        assert options["yAxis"]["type"] == "category"
        assert options["xAxis"]["type"] == "value"

    def test_the_first_row_lands_at_the_top(self) -> None:
        # ECharts fills a category axis bottom-up, so both the labels and the
        # data are reversed here — the chart then reads in the same order as
        # the rows it was given. Which row comes first is the query's business
        # (`ORDER BY metric DESC` in the service), not this function's.
        options = report_chart_options(_result(), "bar", is_dark=False)
        assert options["yAxis"]["data"] == ["Fun", "Rent", "Food"]
        assert [d["value"] for d in options["series"][0]["data"]] == [200.0, 500.0, 300.0]

    def test_a_label_keeps_the_value_it_arrived_with(self) -> None:
        # The reversal pairs labels and values by position; getting it wrong
        # would put every number against the wrong name.
        options = report_chart_options(_result(), "bar", is_dark=False)
        paired = dict(
            zip(
                options["yAxis"]["data"],
                [d["value"] for d in options["series"][0]["data"]],
                strict=True,
            )
        )
        assert paired == {"Food": 300.0, "Rent": 500.0, "Fun": 200.0}

    def test_each_bar_carries_its_value_and_its_share(self) -> None:
        options = report_chart_options(_result(), "bar", is_dark=False)
        data = options["series"][0]["data"]
        assert [d["share"] for d in data] == [20.0, 50.0, 30.0]
        assert "{@value}" in options["series"][0]["label"]["formatter"]
        assert "{@share}" in options["series"][0]["label"]["formatter"]

    def test_the_bars_take_a_colour_from_the_app_palette(self) -> None:
        options = report_chart_options(_result(), "bar", is_dark=False)
        assert options["series"][0]["itemStyle"]["color"] in chart_palette(False)

    def test_dark_mode_changes_the_colours_and_not_the_data(self) -> None:
        light = report_chart_options(_result(), "bar", is_dark=False)
        dark = report_chart_options(_result(), "bar", is_dark=True)
        assert light["yAxis"]["data"] == dark["yAxis"]["data"]
        assert light["series"][0]["itemStyle"]["color"] != dark["series"][0]["itemStyle"]["color"]

    def test_an_empty_result_still_produces_a_drawable_option(self) -> None:
        options = report_chart_options(_result([], []), "bar", is_dark=False)
        assert options["series"][0]["data"] == []
        assert options["yAxis"]["data"] == []


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
        for chart_type in ("bar", "line", "pie", "donut"):
            options = report_chart_options(_result(), chart_type, is_dark=False)
            assert options["color"] == chart_palette(False)


class TestShareRounding:
    def test_a_third_is_not_labelled_to_fifteen_decimal_places(self) -> None:
        # The label prints the share verbatim, so an exact float would read
        # "33.333333333333336%" — precision the chart does not have.
        options = report_chart_options(_result(["A", "B", "C"], [1.0, 1.0, 1.0]), "bar", False)
        assert [d["share"] for d in options["series"][0]["data"]] == [33.3, 33.3, 33.3]
