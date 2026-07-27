# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for full ledger CSV export."""

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
from kaleta.services.transaction_service import LEDGER_CSV_HEADERS


@pytest.mark.asyncio
async def test_export_ledger_csv_headers_and_row(session: AsyncSession) -> None:
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

    raw = await TransactionService(session).export_ledger_csv()
    text = raw.decode("utf-8")
    lines = text.strip().splitlines()
    assert (
        lines[0]
        == "date,type,amount,currency,account,category,payee,description,tags,is_internal_transfer"
    )
    assert lines[0] == ",".join(LEDGER_CSV_HEADERS)
    assert "2026-01-15" in lines[1]
    assert "expense" in lines[1]
    assert "12.50" in lines[1]
    assert "Checking" in lines[1]
    assert "Food" in lines[1]
    assert "Groceries" in lines[1]
