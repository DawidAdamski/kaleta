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
