# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration coverage for full ledger CSV export.

Covers: KAL-SET-020
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.account import AccountType
from kaleta.models.category import CategoryType
from kaleta.models.transaction import TransactionType
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.category import CategoryCreate
from kaleta.schemas.transaction import TransactionCreate
from kaleta.services import AccountService, CategoryService, TransactionService


@pytest.mark.asyncio
async def test_ledger_csv_export_headers(session: AsyncSession) -> None:
    """Covers: KAL-SET-020"""
    account = await AccountService(session).create(
        AccountCreate(name="Checking", type=AccountType.CHECKING, balance=Decimal("100.00"))
    )
    category = await CategoryService(session).create(
        CategoryCreate(name="Food", type=CategoryType.EXPENSE)
    )
    await TransactionService(session).create(
        TransactionCreate(
            account_id=account.id,
            category_id=category.id,
            amount=Decimal("12.50"),
            type=TransactionType.EXPENSE,
            date=date(2026, 1, 15),
            description="Groceries",
        )
    )

    text = (await TransactionService(session).export_ledger_csv()).decode("utf-8")
    header = text.strip().splitlines()[0]
    assert (
        header
        == "date,type,amount,currency,account,category,payee,description,tags,is_internal_transfer"
    )
    row = text.strip().splitlines()[1]
    assert "2026-01-15" in row
    assert "expense" in row
    assert "12.50" in row
    assert "Checking" in row
    assert "Food" in row
    assert "Groceries" in row
