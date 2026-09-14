# SPDX-License-Identifier: AGPL-3.0-or-later
"""The dashboard's amount strings follow the ledger's sign convention.

Covers: KAL-TXN-015 — the ledger and the dashboard read the same money, so
they must not disagree about what a sign means, zero included. The card
helper delegates to ``TransactionService``; these pin what that buys.
"""

from __future__ import annotations

from decimal import Decimal

from kaleta.schemas.transaction import TransactionType
from kaleta.views.components.amount_label import format_signed_amount


class TestFormatSignedAmount:
    def test_income_is_money_in(self) -> None:
        assert format_signed_amount(Decimal("9240.00"), TransactionType.INCOME) == "+9,240.00"

    def test_expense_is_money_out(self) -> None:
        assert format_signed_amount(Decimal("128.74"), TransactionType.EXPENSE) == "-128.74"

    def test_a_float_is_accepted_too(self) -> None:
        # The planned-occurrence cards hold plain numbers.
        assert format_signed_amount(128.74, TransactionType.EXPENSE) == "-128.74"

    def test_zero_carries_no_sign(self) -> None:
        assert format_signed_amount(Decimal("0"), TransactionType.EXPENSE) == "0.00"
        assert format_signed_amount(Decimal("0"), TransactionType.INCOME) == "0.00"
