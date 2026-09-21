# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for the renderings artboard `1f` asks for on a phone.

Covers: KAL-DSH-007

The renderings themselves need a NiceGUI client, but what makes them the
artboard's rather than the grid's is pure: the ECharts options the Month
band's chart is built from, and the second line of a Latest row. Both are
tested here, against the values `1f.html` sets.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pytest

from kaleta.services.report_service import MonthCashflow
from kaleta.views.chart_utils import CHART_GRID_LIGHT, CHART_INK
from kaleta.views.dashboard_widgets import cashflow_chart
from kaleta.views.dashboard_widgets.cashflow_chart import (
    _build_cashflow_chart,
    _month_axis_labels,
)
from kaleta.views.dashboard_widgets.recent_transactions import _row_meta


def _months(n: int = 6) -> list[MonthCashflow]:
    """*n* months ending in July, so the last label is a known "Jul"."""
    return [
        MonthCashflow(
            year=2026,
            month=month,
            income=Decimal("9240.00"),
            expenses=Decimal("6812.00"),
        )
        for month in range(8 - n, 8)
    ]


def _series(opts: dict[str, Any], name_of: str) -> dict[str, Any] | None:
    for series in opts["series"]:
        if series["type"] == name_of:
            return series
    return None


class TestTheMonthBandChart:
    """`1f`: 120px of bars, month letters, and nothing else."""

    def test_the_wide_chart_keeps_its_net_line(self) -> None:
        opts = _build_cashflow_chart(_months(), is_dark=False)

        assert _series(opts, "line") is not None

    def test_the_phone_chart_has_bars_only(self) -> None:
        """A line is read off a scale, and the scale is what 120px gives up."""
        opts = _build_cashflow_chart(_months(), is_dark=False, narrow=True)

        assert _series(opts, "line") is None
        assert [s["name"] for s in opts["series"]] == ["Income", "Expense"]

    def test_the_phone_chart_drops_the_axis_figures_and_the_gridlines(self) -> None:
        """40px of a 350px content width, spent repeating the In/Out figures
        standing directly above the chart."""
        opts = _build_cashflow_chart(_months(), is_dark=False, narrow=True)

        assert opts["yAxis"]["axisLabel"]["show"] is False
        assert opts["yAxis"]["splitLine"]["show"] is False

    def test_the_phone_chart_draws_the_one_rule_the_artboard_does(self) -> None:
        """`1f`'s `#D8D0BC` line at zero — in at zero, out below it."""
        opts = _build_cashflow_chart(_months(), is_dark=False, narrow=True)

        expense = opts["series"][1]
        assert expense["name"] == "Expense"
        assert expense["markLine"]["data"] == [{"yAxis": 0}]
        assert expense["markLine"]["lineStyle"]["color"] == CHART_GRID_LIGHT
        assert expense["markLine"]["label"]["show"] is False

    def test_the_wide_chart_has_no_mark_line(self) -> None:
        """It has gridlines and a labelled axis; the rule would be a fourth
        line through a chart that already says where zero is."""
        opts = _build_cashflow_chart(_months(), is_dark=False)

        assert all("markLine" not in series for series in opts["series"])

    def test_the_phone_bars_are_the_artboard_share(self) -> None:
        """26px on a 56px step, against `1c`'s 50 on 182."""
        narrow = _build_cashflow_chart(_months(), is_dark=False, narrow=True)
        wide = _build_cashflow_chart(_months(), is_dark=False)

        assert narrow["series"][0]["barWidth"] == "46%"
        assert wide["series"][0]["barWidth"] == "27%"


class TestTheMonthAxisLabels:
    def test_every_month_is_named(self) -> None:
        """ECharts thins a crowded axis by itself; `1f` names all six."""
        assert _month_axis_labels(_months(), is_dark=False)["interval"] == 0

    def test_the_month_in_progress_is_tagged_for_the_ink_style(self) -> None:
        labels = _month_axis_labels(_months(), is_dark=False)

        assert '"Jul"' in labels[":formatter"]
        assert labels["rich"]["cur"]["fontWeight"] == 600
        assert labels["rich"]["cur"]["color"] == CHART_INK

    def test_no_months_means_nothing_to_tag(self) -> None:
        labels = _month_axis_labels([], is_dark=False)

        assert ":formatter" not in labels
        assert "rich" not in labels

    def test_a_label_carrying_rich_text_markup_is_left_plain(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ECharts' rich text has no escape, so `{`, `}` and `|` cannot be
        tagged — a label carrying one would be read as markup instead of
        printed. No month abbreviation does today, and a translation is not
        this module's to promise, so the label is patched to prove the guard
        rather than to describe a locale that exists.
        """
        months = _months(1)
        assert ":formatter" in _month_axis_labels(months, is_dark=False)

        monkeypatch.setattr(cashflow_chart, "_month_label", lambda _m: "Ju|l")
        guarded = _month_axis_labels(months, is_dark=False)

        assert ":formatter" not in guarded
        assert "rich" not in guarded
        assert guarded["interval"] == 0


@dataclass
class _Category:
    name: str


@dataclass
class _Tx:
    """Just the two fields the second line of a Latest row reads."""

    date: datetime.date
    category: _Category | None


class TestTheLatestRowMeta:
    """`1f` writes "03.07 · Żywność" — day, then month, then the category."""

    def test_the_date_comes_first_day_before_month(self) -> None:
        row = _Tx(datetime.date(2026, 7, 3), _Category("Żywność"))

        assert _row_meta(row) == "03.07 · Żywność"  # type: ignore[arg-type]

    def test_a_row_with_no_category_is_the_date_alone(self) -> None:
        """A missing category is not a second fact about the movement, so it
        does not get an em dash of its own on the line."""
        row = _Tx(datetime.date(2026, 12, 31), None)

        assert _row_meta(row) == "31.12"  # type: ignore[arg-type]
