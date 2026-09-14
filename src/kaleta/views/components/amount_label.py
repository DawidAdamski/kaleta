# SPDX-License-Identifier: AGPL-3.0-or-later
"""Semantic amount colouring for transaction tables and labels."""

from __future__ import annotations

from decimal import Decimal

from kaleta.schemas.transaction import TransactionType
from kaleta.services import TransactionService
from kaleta.views.theme import AMOUNT_EXPENSE, AMOUNT_INCOME, AMOUNT_NEUTRAL, amount_class


def format_signed_amount(amount: Decimal | float, tx_type: TransactionType) -> str:
    """Format an amount with its sign, for views holding a plain number.

    The convention itself lives in ``TransactionService`` — the dashboard and
    the ledger must not disagree about what a minus sign means, or about
    whether a zero carries one.
    """
    return TransactionService.format_signed_amount(Decimal(str(amount)), tx_type)


def signed_amount_class(amount: Decimal | float, tx_type: TransactionType) -> str:
    """The tone for one row's figure — zero moved nothing, so it is neither."""
    return AMOUNT_NEUTRAL if Decimal(str(amount)) == 0 else amount_class(tx_type.value)


def net_tone(net: Decimal) -> str:
    """The tone for a total, which has no type of its own — only a direction."""
    if net > 0:
        return AMOUNT_INCOME
    if net < 0:
        return AMOUNT_EXPENSE
    return AMOUNT_NEUTRAL


def amount_cell_slot() -> str:
    """Vue ``q-td`` fragment for a colour-coded amount column in ``ui.table`` body slots."""
    return (
        '<q-td key="amount" :props="props" class="text-right">'
        # A zero moved nothing, so it is neither income nor expense — the
        # server-side rule is ``signed_amount_class``. A row that carries no
        # ``amount_value`` gives NaN and falls through to the type; the null
        # guard keeps a row that sends an explicit null from reading as zero.
        f'<span :class="props.row.amount_value != null '
        f"&& Number(props.row.amount_value) === 0 ? '{AMOUNT_NEUTRAL}' : "
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
