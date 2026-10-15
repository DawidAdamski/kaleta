# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for the bulk change-category gating helper.

Covers: KAL-TXN-022 — the selection bar only offers "Change category" when a
single income/expense type can take one.
"""

from __future__ import annotations

from kaleta.views.transactions.bulk_category_dialog import assignable_category_type


def _row(tx_type: str, *, has_splits: bool = False) -> dict[str, object]:
    return {"id": 1, "type": tx_type, "has_splits": has_splits}


def test_all_expense_rows_are_assignable_as_expense() -> None:
    rows = [_row("expense"), _row("expense")]
    assert assignable_category_type(rows) == "expense"


def test_all_income_rows_are_assignable_as_income() -> None:
    assert assignable_category_type([_row("income")]) == "income"


def test_mixed_types_are_not_assignable() -> None:
    assert assignable_category_type([_row("expense"), _row("income")]) is None


def test_transfer_rows_are_not_assignable() -> None:
    assert assignable_category_type([_row("transfer")]) is None


def test_a_split_row_blocks_the_whole_selection() -> None:
    assert assignable_category_type([_row("expense"), _row("expense", has_splits=True)]) is None


def test_empty_selection_is_not_assignable() -> None:
    assert assignable_category_type([]) is None
