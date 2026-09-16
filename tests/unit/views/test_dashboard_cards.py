# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for the figure formatting behind the merged dashboard cards."""

from __future__ import annotations

from decimal import Decimal

from kaleta.views.dashboard_widgets.constants import SEVERE_SPENT_PCT
from kaleta.views.dashboard_widgets.helpers import fmt_number, split_amount

#: The threshold as the plan states it, not as the module computes it.
_THRESHOLD = Decimal("110")


def test_the_shipped_threshold_is_the_one_the_plan_chose() -> None:
    # The colour rule itself is tested on BudgetVarianceRow, next to the
    # figures it reads; what belongs here is the number the widget hands it.
    assert SEVERE_SPENT_PCT == _THRESHOLD


class TestFigureFormatting:
    def test_fmt_number_drops_only_the_currency(self) -> None:
        assert fmt_number(Decimal("64648.01")) == "64,648.01"

    def test_split_amount_peels_off_the_decimals(self) -> None:
        # The thousands separator is a comma, so the split must key on the dot.
        assert split_amount(Decimal("64648.01")) == ("64,648", ".01")

    def test_split_amount_keeps_a_negative_sign_with_the_whole_part(self) -> None:
        assert split_amount(Decimal("-1234.50")) == ("-1,234", ".50")
