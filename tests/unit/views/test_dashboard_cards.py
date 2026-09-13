# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for the pure helpers behind the merged dashboard cards."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from kaleta.views.dashboard_widgets.balance_card import top_accounts
from kaleta.views.dashboard_widgets.helpers import fmt_number, split_amount


@dataclass
class _Account:
    name: str
    balance: Decimal


def _accounts(*pairs: tuple[str, str]) -> list[_Account]:
    return [_Account(name, Decimal(value)) for name, value in pairs]


class TestTopAccounts:
    def test_fewer_than_the_limit_are_all_shown(self) -> None:
        accounts = _accounts(("PKO", "1200.00"), ("Revolut", "300.00"))

        shown, hidden, hidden_total = top_accounts(accounts)

        assert [a.name for a in shown] == ["PKO", "Revolut"]
        assert hidden == 0
        assert hidden_total == Decimal("0")

    def test_the_largest_lead_regardless_of_name(self) -> None:
        accounts = _accounts(
            ("Alfa", "10.00"), ("Beta", "9000.00"), ("Gamma", "500.00"), ("Delta", "40.00")
        )

        shown, _hidden, _total = top_accounts(accounts)

        assert [a.name for a in shown] == ["Beta", "Gamma", "Delta"]

    def test_the_remainder_is_counted_and_summed(self) -> None:
        accounts = _accounts(
            ("A", "100.00"), ("B", "90.00"), ("C", "80.00"), ("D", "7.50"), ("E", "2.50")
        )

        shown, hidden, hidden_total = top_accounts(accounts)

        assert [a.name for a in shown] == ["A", "B", "C"]
        assert hidden == 2
        # The tiles must add up to the hero: 270 shown + 10 hidden = 280 total.
        assert hidden_total == Decimal("10.00")
        assert sum(a.balance for a in shown) + hidden_total == Decimal("280.00")

    def test_no_accounts_at_all(self) -> None:
        assert top_accounts([]) == ([], 0, Decimal("0"))


class TestFigureFormatting:
    def test_fmt_number_drops_only_the_currency(self) -> None:
        assert fmt_number(Decimal("64648.01")) == "64,648.01"

    def test_split_amount_peels_off_the_decimals(self) -> None:
        # The thousands separator is a comma, so the split must key on the dot.
        assert split_amount(Decimal("64648.01")) == ("64,648", ".01")

    def test_split_amount_keeps_a_negative_sign_with_the_whole_part(self) -> None:
        assert split_amount(Decimal("-1234.50")) == ("-1,234", ".50")
