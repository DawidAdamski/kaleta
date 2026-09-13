# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for the figure formatting behind the merged dashboard cards."""

from __future__ import annotations

from decimal import Decimal

from kaleta.services.report_service import BudgetVarianceRow
from kaleta.views.dashboard_widgets.budget_variance_month import _SEVERE_SPENT_PCT
from kaleta.views.dashboard_widgets.helpers import fmt_number, split_amount


def _is_severe(planned: str, actual: str) -> bool:
    """How ``_variance_row`` decides between the expense and warning colour."""
    row = BudgetVarianceRow(category="x", planned=Decimal(planned), actual=Decimal(actual))
    spent = row.spent_pct
    return spent is None or spent >= _SEVERE_SPENT_PCT


class TestVarianceSeverity:
    """The three over-budget rows drawn in artboard 1c, and how they colour."""

    def test_fifteen_percent_over_reads_as_expense(self) -> None:
        assert _is_severe("1400.00", "1612.30") is True

    def test_thirty_nine_percent_over_reads_as_expense(self) -> None:
        assert _is_severe("300.00", "418.00") is True

    def test_six_percent_over_reads_as_a_warning(self) -> None:
        assert _is_severe("350.00", "372.40") is False

    def test_exactly_at_the_threshold_reads_as_expense(self) -> None:
        assert _is_severe("100.00", "110.00") is True


class TestFigureFormatting:
    def test_fmt_number_drops_only_the_currency(self) -> None:
        assert fmt_number(Decimal("64648.01")) == "64,648.01"

    def test_split_amount_peels_off_the_decimals(self) -> None:
        # The thousands separator is a comma, so the split must key on the dot.
        assert split_amount(Decimal("64648.01")) == ("64,648", ".01")

    def test_split_amount_keeps_a_negative_sign_with_the_whole_part(self) -> None:
        assert split_amount(Decimal("-1234.50")) == ("-1,234", ".50")
