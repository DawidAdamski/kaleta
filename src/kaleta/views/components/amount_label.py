# SPDX-License-Identifier: AGPL-3.0-or-later
"""Semantic amount colouring for transaction tables and labels."""

from __future__ import annotations

from decimal import Decimal

from kaleta.schemas.transaction import TransactionType
from kaleta.services import TransactionService
from kaleta.views.theme import AMOUNT_EXPENSE, AMOUNT_INCOME, AMOUNT_NEUTRAL, amount_class


def format_signed_amount(amount: Decimal | float, tx_type: str) -> str:
    """Format an amount with its sign, for callers holding the type as a string.

    The convention itself lives in ``TransactionService`` — the dashboard and
    the ledger must not disagree about what a minus sign means, or about
    whether a zero carries one.
    """
    return TransactionService.format_signed_amount(Decimal(str(amount)), TransactionType(tx_type))


def amount_cell_slot() -> str:
    """Vue ``q-td`` fragment for a colour-coded amount column in ``ui.table`` body slots."""
    return (
        '<q-td key="amount" :props="props" class="text-right">'
        # A zero moved nothing, so it is neither income nor expense. Rows
        # without an ``amount_value`` (other tables reuse this slot) give NaN,
        # which is not zero, and fall through to the type as before.
        f"<span :class=\"Number(props.row.amount_value) === 0 ? '{AMOUNT_NEUTRAL}' : "
        f"props.row.type === 'income' ? '{AMOUNT_INCOME}' : "
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
