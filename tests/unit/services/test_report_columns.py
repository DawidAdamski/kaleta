# SPDX-License-Identifier: AGPL-3.0-or-later
"""Derived report columns — share, rank, change, moving average.

Covers the arithmetic behind KAL-RPT-008..010; the scenarios themselves run
end to end in ``tests/e2e/test_reports_builder.py``.
"""

from __future__ import annotations

import pytest

from kaleta.services.report_columns import (
    derive,
    fill_time_axis,
    moving_averages,
    percent_changes,
    ranks,
    shares,
)
from kaleta.services.saved_report_service import PivotResult, ReportConfig, ReportResult


def _monthly(labels: list[str], values: list[float]) -> ReportResult:
    return ReportResult(
        labels=labels, values=values, column_header="Month", metric_header="Total Amount"
    )


def _pivot(series: list[str], cells: list[list[float]]) -> PivotResult:
    return PivotResult(
        row_header="Category",
        series_header="Month",
        row_labels=["Groceries", "Fuel"][: len(cells)],
        series_labels=series,
        cells=cells,
        metric_header="Total Amount",
        row_totals=[sum(row) for row in cells],
        series_totals=[sum(column) for column in zip(*cells, strict=True)],
    )


class TestShare:
    def test_shares_add_up_to_a_hundred(self) -> None:
        assert sum(shares([300.0, 500.0, 200.0])) == pytest.approx(100.0)
        assert shares([300.0, 500.0, 200.0]) == pytest.approx((30.0, 50.0, 20.0))

    def test_a_total_of_nothing_has_no_shares(self) -> None:
        assert shares([0.0, 0.0]) == (0.0, 0.0)


class TestRank:
    def test_largest_first(self) -> None:
        assert ranks([200.0, 500.0, 300.0]) == (3, 1, 2)

    def test_ties_share_a_place_and_skip_the_next(self) -> None:
        assert ranks([500.0, 500.0, 100.0]) == (1, 1, 3)


class TestChange:
    def test_change_from_zero_is_none_not_infinity(self) -> None:
        assert percent_changes([0.0, 120.0]) == (None, None)

    def test_a_drop_to_zero_is_minus_a_hundred(self) -> None:
        assert percent_changes([200.0, 0.0]) == (None, -100.0)

    def test_the_first_period_has_no_change(self) -> None:
        line = derive(_monthly(["2025-01", "2025-02"], [100.0, 150.0]), ["change"], 3).lines[0]
        assert line.change == (None, 50.0)
        assert line.change_pct == (None, 50.0)


class TestMovingAverage:
    def test_trailing_window_includes_the_current_period(self) -> None:
        assert moving_averages([30.0, 60.0, 90.0, 120.0], 3) == (None, None, 60.0, 90.0)

    def test_a_window_longer_than_the_history_has_no_average(self) -> None:
        assert moving_averages([30.0, 60.0], 3) == (None, None)

    def test_a_window_shorter_than_history_slides(self) -> None:
        assert moving_averages([10.0, 20.0, 30.0, 40.0, 50.0], 2) == (
            None,
            15.0,
            25.0,
            35.0,
            45.0,
        )


class TestFillTimeAxis:
    def test_a_missing_month_is_a_zero(self) -> None:
        filled = fill_time_axis(_monthly(["2025-03", "2025-01"], [50.0, 100.0]), "month")
        assert isinstance(filled, ReportResult)
        assert filled.labels == ["2025-01", "2025-02", "2025-03"]
        assert filled.values == [100.0, 0.0, 50.0]

    def test_the_gap_reads_as_a_full_drop(self) -> None:
        filled = fill_time_axis(_monthly(["2025-01", "2025-03"], [100.0, 50.0]), "month")
        line = derive(filled, ["change"], 3).lines[0]
        assert line.change_pct == (None, -100.0, None)

    def test_the_fill_crosses_a_year_end(self) -> None:
        filled = fill_time_axis(_monthly(["2024-12", "2025-02"], [1.0, 2.0]), "month")
        assert isinstance(filled, ReportResult)
        assert filled.labels == ["2024-12", "2025-01", "2025-02"]

    def test_years_fill_too(self) -> None:
        filled = fill_time_axis(_monthly(["2023", "2025"], [1.0, 2.0]), "year")
        assert isinstance(filled, ReportResult)
        assert filled.labels == ["2023", "2024", "2025"]

    def test_a_pivot_series_is_filled_for_every_row(self) -> None:
        filled = fill_time_axis(_pivot(["2025-01", "2025-03"], [[10.0, 30.0]]), "month")
        assert isinstance(filled, PivotResult)
        assert filled.series_labels == ["2025-01", "2025-02", "2025-03"]
        assert filled.cells == [[10.0, 0.0, 30.0]]
        assert filled.series_totals == [10.0, 0.0, 30.0]

    def test_a_label_that_is_not_a_period_leaves_the_result_alone(self) -> None:
        result = _monthly(["—", "2025-01"], [1.0, 2.0])
        assert fill_time_axis(result, "month") is result


class TestPivotDerivation:
    def test_change_runs_along_each_row(self) -> None:
        """Covers: KAL-RPT-009"""
        pivot = _pivot(["2025-01", "2025-02"], [[9000.0, 7000.0], [100.0, 300.0]])
        derived = derive(pivot, ["change"], 3)
        assert derived.lines[0].change == (None, -2000.0)
        assert derived.lines[1].change == (None, 200.0)
        assert derived.lines[1].change_pct == (None, 200.0)

    def test_share_is_of_the_series_column(self) -> None:
        pivot = _pivot(["2025-01", "2025-02"], [[300.0, 100.0], [100.0, 100.0]])
        derived = derive(pivot, ["share", "rank"], 3)
        assert derived.lines[0].share == pytest.approx((75.0, 50.0))
        assert derived.lines[1].share == pytest.approx((25.0, 50.0))
        assert derived.lines[0].rank == (1, 1)
        assert derived.lines[1].rank == (2, 1)

    def test_columns_not_asked_for_are_absent(self) -> None:
        line = derive(_pivot(["2025-01"], [[1.0]]), ["share"], 3).lines[0]
        assert line.change is None
        assert line.moving_avg is None
        assert line.rank is None


class TestActiveColumns:
    def test_a_category_report_drops_the_trend_columns(self) -> None:
        """Covers: KAL-RPT-010"""
        config = ReportConfig(dimension="category", columns=["moving_avg", "share", "change"])
        assert config.active_columns() == ["share"]

    def test_a_monthly_report_keeps_them_in_canonical_order(self) -> None:
        """Covers: KAL-RPT-008"""
        config = ReportConfig(dimension="month", columns=["moving_avg", "share"])
        assert config.active_columns() == ["share", "moving_avg"]

    def test_a_weekday_is_not_a_trend_axis(self) -> None:
        config = ReportConfig(dimension="weekday", columns=["change"])
        assert config.active_columns() == []

    def test_on_a_pivot_the_series_is_the_axis(self) -> None:
        config = ReportConfig(dimension="category", series="month", columns=["change"])
        assert config.active_columns() == ["change"]
        flipped = ReportConfig(dimension="month", series="category", columns=["change"])
        assert flipped.active_columns() == []
