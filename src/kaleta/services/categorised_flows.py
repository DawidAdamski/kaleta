# SPDX-License-Identifier: AGPL-3.0-or-later
"""Normalised category-attributed transaction amounts for reporting."""

from __future__ import annotations

from sqlalchemy import select, union_all
from sqlalchemy.sql.selectable import Subquery

from kaleta.models.transaction import Transaction, TransactionSplit


def categorised_flows_selectable() -> Subquery:
    """Return a subquery of category-attributed amount rows.

    Non-split transactions contribute one row from ``Transaction.category_id``.
    Split transactions contribute one row per ``TransactionSplit`` line.
    """
    non_split = select(
        Transaction.id.label("transaction_id"),
        Transaction.category_id.label("category_id"),
        Transaction.amount.label("amount"),
        Transaction.date.label("date"),
        Transaction.type.label("type"),
        Transaction.account_id.label("account_id"),
        Transaction.user_id.label("user_id"),
        Transaction.is_internal_transfer.label("is_internal_transfer"),
    ).where(Transaction.is_split == False)  # noqa: E712
    split = (
        select(
            Transaction.id.label("transaction_id"),
            TransactionSplit.category_id.label("category_id"),
            TransactionSplit.amount.label("amount"),
            Transaction.date.label("date"),
            Transaction.type.label("type"),
            Transaction.account_id.label("account_id"),
            Transaction.user_id.label("user_id"),
            Transaction.is_internal_transfer.label("is_internal_transfer"),
        )
        .join(TransactionSplit, TransactionSplit.transaction_id == Transaction.id)
        .where(Transaction.is_split == True)  # noqa: E712
    )
    return union_all(non_split, split).subquery("categorised_flows")
