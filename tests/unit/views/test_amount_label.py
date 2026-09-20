# SPDX-License-Identifier: AGPL-3.0-or-later
"""The dashboard's amount strings follow the ledger's sign convention.

Covers: KAL-TXN-017 — the ledger and the dashboard read the same money, so
they must not disagree about what a sign means, zero included. The card
helper delegates to ``TransactionService``; these pin what that buys.
"""

from __future__ import annotations

from decimal import Decimal

from kaleta.schemas.transaction import TransactionType
from kaleta.views.components.amount_label import (
    format_signed_amount,
    net_tone,
    signed_amount_class,
    spaced_thousands,
)
from kaleta.views.theme import AMOUNT_EXPENSE, AMOUNT_INCOME, AMOUNT_NEUTRAL


class TestFormatSignedAmount:
    def test_income_is_money_in(self) -> None:
        assert format_signed_amount(Decimal("9240.00"), TransactionType.INCOME) == "+9,240.00"

    def test_expense_is_money_out(self) -> None:
        assert format_signed_amount(Decimal("128.74"), TransactionType.EXPENSE) == "-128.74"

    def test_a_float_is_accepted_too(self) -> None:
        # The planned-occurrence cards hold plain numbers.
        assert format_signed_amount(128.74, TransactionType.EXPENSE) == "-128.74"

    def test_zero_carries_no_sign(self) -> None:
        """Covers: KAL-TXN-017"""
        assert format_signed_amount(Decimal("0"), TransactionType.EXPENSE) == "0.00"
        assert format_signed_amount(Decimal("0"), TransactionType.INCOME) == "0.00"


class TestTone:
    """A zero has no direction, so nothing paints it as if it had one."""

    def test_a_row_takes_its_type(self) -> None:
        assert signed_amount_class(Decimal("128.74"), TransactionType.EXPENSE) == AMOUNT_EXPENSE
        assert signed_amount_class(Decimal("9240.00"), TransactionType.INCOME) == AMOUNT_INCOME

    def test_a_zero_row_is_neutral_whatever_its_type(self) -> None:
        """Covers: KAL-TXN-017"""
        assert signed_amount_class(Decimal("0"), TransactionType.EXPENSE) == AMOUNT_NEUTRAL
        assert signed_amount_class(Decimal("0"), TransactionType.INCOME) == AMOUNT_NEUTRAL

    def test_a_total_takes_its_sign(self) -> None:
        assert net_tone(Decimal("9111.26")) == AMOUNT_INCOME
        assert net_tone(Decimal("-128.74")) == AMOUNT_EXPENSE

    def test_a_zero_total_is_neutral(self) -> None:
        """Covers: KAL-TXN-015 — a transfer pair nets to nothing, in no colour."""
        assert net_tone(Decimal("0")) == AMOUNT_NEUTRAL


class TestSpacedThousands:
    """The grouping the restyled screens write (every artboard draws it).

    Python's `,` is the only grouping `format` offers; the artboards, and
    Polish typography, put a space there. One function, so a screen cannot
    write it both ways — the report builder's total and the day sheet's
    figures used to each do their own `.replace`.
    """

    def test_a_comma_becomes_a_space(self) -> None:
        assert spaced_thousands(f"{9600:,.2f}") == "9 600.00"

    def test_every_group_of_a_large_figure(self) -> None:
        assert spaced_thousands(f"{4218901:,}") == "4 218 901"

    def test_the_decimal_point_is_left_alone(self) -> None:
        assert spaced_thousands("24,279.31") == "24 279.31"

    def test_a_figure_with_no_group_is_unchanged(self) -> None:
        assert spaced_thousands("99.00") == "99.00"

    def test_a_suffix_survives(self) -> None:
        assert spaced_thousands("1,234.50 zł") == "1 234.50 zł"
