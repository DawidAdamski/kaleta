# SPDX-License-Identifier: AGPL-3.0-or-later
"""The irregular-expenses fund's plan: items at a tenth a month, the total, the transfer.

``funds-irregular-items`` Part A. Expected figures are the scenarios' literals.

Covers: KAL-IRR-001, KAL-IRR-002, KAL-IRR-003
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import ConflictError, ValidationError
from kaleta.models.account import AccountType
from kaleta.models.planned_transaction import RecurrenceFrequency
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.irregular_item import IrregularFundingCreate, IrregularItemCreate
from kaleta.schemas.reserve_fund import ReserveFundCreate, ReserveFundKind
from kaleta.schemas.transaction import TransactionType
from kaleta.services import (
    AccountService,
    IrregularItemService,
    PlannedTransactionService,
    ReserveFundService,
)

START = datetime.date(2026, 11, 1)


class _Fund:
    def __init__(self, session: AsyncSession) -> None:
        self.accounts = AccountService(session)
        self.funds = ReserveFundService(session)
        self.items = IrregularItemService(session)
        self.planned = PlannedTransactionService(session)

    async def account(self, name: str) -> int:
        created = await self.accounts.create(
            AccountCreate(name=name, type=AccountType.SAVINGS, balance=Decimal("0.00"))
        )
        return created.id

    async def fund(self, backing_id: int, kind: ReserveFundKind = ReserveFundKind.IRREGULAR) -> int:
        fund = await self.funds.create(
            ReserveFundCreate(
                name="Wydatki nieregularne",
                kind=kind,
                target_amount=Decimal("3000.00"),
                backing_account_id=backing_id,
            )
        )
        return fund.id

    async def item(self, fund_id: int, name: str, yearly: str) -> None:
        await self.items.create(
            fund_id, IrregularItemCreate(name=name, yearly_amount=Decimal(yearly))
        )


@pytest.fixture
async def fund(session: AsyncSession) -> _Fund:
    return _Fund(session)


async def test_an_item_is_set_aside_at_a_tenth_a_month(fund: _Fund) -> None:
    """Covers: KAL-IRR-001"""
    fund_id = await fund.fund(await fund.account("Konto funduszu"))
    await fund.item(fund_id, "Car insurance", "1200.00")

    plan = await fund.items.plan(fund_id)
    assert [(i.name, i.yearly_amount, i.monthly_contribution) for i in plan.items] == [
        ("Car insurance", Decimal("1200.00"), Decimal("120.00"))
    ]


async def test_the_fund_asks_for_the_sum_of_its_items(fund: _Fund) -> None:
    """Covers: KAL-IRR-002"""
    fund_id = await fund.fund(await fund.account("Konto funduszu"))
    await fund.item(fund_id, "Car insurance", "1200.00")
    await fund.item(fund_id, "Property tax", "600.00")

    plan = await fund.items.plan(fund_id)
    assert plan.monthly_total == Decimal("180.00")
    assert plan.yearly_total == Decimal("1800.00")


async def test_only_an_irregular_fund_has_items(fund: _Fund) -> None:
    emergency = await fund.fund(await fund.account("Poduszka"), ReserveFundKind.EMERGENCY)
    with pytest.raises(ValidationError):
        await fund.item(emergency, "Car insurance", "1200.00")


async def test_the_contribution_becomes_a_monthly_planned_transfer(fund: _Fund) -> None:
    """Covers: KAL-IRR-003"""
    backing = await fund.account("Konto funduszu")
    source = await fund.account("Konto główne")
    fund_id = await fund.fund(backing)
    await fund.item(fund_id, "Car insurance", "1200.00")
    await fund.item(fund_id, "Property tax", "600.00")

    payload = IrregularFundingCreate(from_account_id=source, start_date=START)
    await fund.items.create_funding_plan(fund_id, payload)

    [planned] = await fund.planned.list()
    assert planned.type is TransactionType.TRANSFER
    assert planned.amount == Decimal("180.00")
    assert planned.frequency is RecurrenceFrequency.MONTHLY
    assert planned.interval == 1
    assert planned.account_id == source
    assert planned.description == "Konto główne → Konto funduszu"
    assert planned.start_date == START

    # Accepting it twice would feed the fund twice.
    with pytest.raises(ConflictError):
        await fund.items.create_funding_plan(fund_id, payload)


async def test_no_transfer_is_planned_from_the_fund_into_itself(fund: _Fund) -> None:
    backing = await fund.account("Konto funduszu")
    fund_id = await fund.fund(backing)
    await fund.item(fund_id, "Car insurance", "1200.00")
    with pytest.raises(ValidationError):
        await fund.items.create_funding_plan(
            fund_id, IrregularFundingCreate(from_account_id=backing, start_date=START)
        )
