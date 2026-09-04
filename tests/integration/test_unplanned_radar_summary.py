# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration coverage for the radar's irregular-expenses-fund roll-up.

Covers: KAL-REC-009
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.account import AccountType
from kaleta.models.category import CategoryType
from kaleta.models.payee import Payee
from kaleta.models.transaction import Transaction, TransactionType
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.category import CategoryCreate
from kaleta.services import AccountService, CategoryService, UnplannedRadarService
from kaleta.services.unplanned_radar_service import summarise

pytestmark = pytest.mark.asyncio

TODAY = datetime.date(2026, 9, 4)


async def _seed_yearly_cost(
    session: AsyncSession,
    *,
    account_id: int,
    category_id: int,
    payee_name: str,
    amount: Decimal,
) -> None:
    payee = Payee(name=payee_name)
    session.add(payee)
    await session.commit()
    await session.refresh(payee)
    for date in (datetime.date(2024, 9, 10), datetime.date(2025, 9, 10)):
        session.add(
            Transaction(
                account_id=account_id,
                category_id=category_id,
                payee_id=payee.id,
                type=TransactionType.EXPENSE,
                amount=amount,
                date=date,
                description=f"{payee_name} {date}",
                is_internal_transfer=False,
            )
        )
    await session.commit()


async def test_fund_line_sums_the_yearly_estimates(session: AsyncSession) -> None:
    """Covers: KAL-REC-009"""
    account = await AccountService(session).create(
        AccountCreate(name="PKO Main", type=AccountType.CHECKING)
    )
    category = await CategoryService(session).create(
        CategoryCreate(name="Dom", type=CategoryType.EXPENSE)
    )
    await _seed_yearly_cost(
        session,
        account_id=account.id,
        category_id=category.id,
        payee_name="Serwis Auto",
        amount=Decimal("1300.00"),
    )
    await _seed_yearly_cost(
        session,
        account_id=account.id,
        category_id=category.id,
        payee_name="Kominiarz",
        amount=Decimal("150.00"),
    )

    candidates = await UnplannedRadarService(session).detect(today=TODAY)
    summary = summarise(candidates)

    assert summary.candidate_count == 2
    assert summary.yearly_total == Decimal("1450.00")
