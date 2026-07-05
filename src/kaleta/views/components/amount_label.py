# SPDX-License-Identifier: AGPL-3.0-or-later
"""Semantic amount colouring for transaction tables and labels."""

from __future__ import annotations

from decimal import Decimal

from kaleta.views.theme import AMOUNT_EXPENSE, AMOUNT_INCOME, AMOUNT_NEUTRAL, amount_class


def format_signed_amount(amount: Decimal | float, tx_type: str) -> str:
    """Format amount with leading sign for display (income +, expense -)."""
    value = Decimal(str(amount))
    if tx_type == "income":
        return f"+{abs(value):,.2f}"
    return f"-{abs(value):,.2f}"


def amount_cell_slot() -> str:
    """Vue ``q-td`` fragment for a colour-coded amount column in ``ui.table`` body slots."""
    return (
        '<q-td key="amount" :props="props" class="text-right">'
        f"<span :class=\"props.row.type === 'income' ? '{AMOUNT_INCOME}' : "
        f"props.row.type === 'expense' ? '{AMOUNT_EXPENSE}' : '{AMOUNT_NEUTRAL}'\">"
        "{{ props.row.amount }}</span></q-td>"
    )


def amount_body_cell_slot(*, type_field: str = "type") -> str:
    """Vue ``body-cell-amount`` slot with semantic amount colouring."""
    return (
        '<q-td :props="props" class="text-right">'
        f"<span :class=\"props.row.{type_field} === 'income' ? '{AMOUNT_INCOME}' : "
        f"props.row.{type_field} === 'expense' ? '{AMOUNT_EXPENSE}' : '{AMOUNT_NEUTRAL}'\">"
        "{{ props.row.amount }}</span></q-td>"
    )


def amount_css_class(tx_type: str) -> str:
    """Return the Tailwind colour class for a transaction type string."""
    return amount_class(tx_type)
