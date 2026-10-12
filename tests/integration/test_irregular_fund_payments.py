# SPDX-License-Identifier: AGPL-3.0-or-later
"""Paying out of the irregular-expenses fund: an item's payment, an unplanned one, the history.

``funds-irregular-items`` Part B. Expected figures are the scenarios' literals.

Covers: KAL-IRR-004, KAL-IRR-005
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import ValidationError
from kaleta.models.account import AccountType
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.category import CategoryCreate, CategoryType
from kaleta.schemas.irregular_item import (
    IrregularEntryKind,
    IrregularItemCreate,
    IrregularPaymentCreate,
)
from kaleta.schemas.reserve_fund import ReserveFundCreate, ReserveFundKind
from kaleta.schemas.transaction import TransactionCreate, TransactionType, TransferDirection
from kaleta.services import (
    AccountService,
    CategoryService,
    IrregularItemService,
    ReserveFundService,
    TransactionService,
)

DAY = datetime.date(2026, 10, 5)


class _Fund:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.items = IrregularItemService(session)

    async def holding(self, balance: str) -> tuple[int, int]:
        """A fund whose account holds ``balance``; return (fund id, account id)."""
        account = await AccountService(self.session).create(
            AccountCreate(name="Konto funduszu", type=AccountType.SAVINGS, balance=Decimal(balance))
        )
        fund = await ReserveFundService(self.session).create(
            ReserveFundCreate(
                name="Wydatki nieregularne",
                kind=ReserveFundKind.IRREGULAR,
                target_amount=Decimal("3000.00"),
                backing_account_id=account.id,
            )
        )
        return fund.id, account.id

    async def category(self, name: str) -> int:
        created = await CategoryService(self.session).create(
            CategoryCreate(name=name, type=CategoryType.EXPENSE)
        )
        return created.id

    async def balance(self, fund_id: int) -> Decimal:
        return (await self.items.plan(fund_id)).balance


@pytest.fixture
async def fund(session: AsyncSession) -> _Fund:
    return _Fund(session)


async def test_paying_an_item_from_the_fund(fund: _Fund) -> None:
    """Covers: KAL-IRR-004"""
    fund_id, _ = await fund.holding("1500.00")
    insurance = await fund.category("Ubezpieczenia")
    item = await fund.items.create(
        fund_id,
        IrregularItemCreate(
            name="Car insurance", yearly_amount=Decimal("1200.00"), category_id=insurance
        ),
    )

    tx = await fund.items.record_payment(
        fund_id, IrregularPaymentCreate(item_id=item.id, amount=Decimal("1250.00"), date=DAY)
    )

    assert tx.irregular_item_id == item.id
    assert tx.category_id == insurance  # the item's own
    assert await fund.balance(fund_id) == Decimal("250.00")
    [entry] = [e for e in await fund.items.history(fund_id) if e.transaction_id == tx.id]
    assert entry.kind is IrregularEntryKind.PAYMENT
    assert entry.item_name == "Car insurance"
    assert entry.amount == Decimal("-1250.00")


async def test_an_unplanned_cost_paid_from_the_fund(fund: _Fund) -> None:
    """Covers: KAL-IRR-005"""
    fund_id, _ = await fund.holding("800.00")
    heating = await fund.category("Ogrzewanie")

    tx = await fund.items.record_payment(
        fund_id,
        IrregularPaymentCreate(
            amount=Decimal("300.00"),
            date=DAY,
            description="heating underpayment",
            category_id=heating,
        ),
    )

    [entry] = await fund.items.history(fund_id)
    assert entry.transaction_id == tx.id
    assert entry.kind is IrregularEntryKind.UNPLANNED
    assert entry.description == "heating underpayment"
    assert await fund.balance(fund_id) == Decimal("500.00")


async def test_a_ledger_expense_is_linked_and_unlinked_from_the_history(fund: _Fund) -> None:
    fund_id, account_id = await fund.holding("800.00")
    cat = await fund.category("Podatki")
    item = await fund.items.create(
        fund_id, IrregularItemCreate(name="Property tax", yearly_amount=Decimal("600.00"))
    )
    # Entered on the ledger (or imported), not through the fund's page.
    tx = await TransactionService(fund.session).create(
        TransactionCreate(
            account_id=account_id,
            category_id=cat,
            amount=Decimal("600.00"),
            type=TransactionType.EXPENSE,
            date=DAY,
            description="Podatek od nieruchomości",
        )
    )
    assert (await fund.items.history(fund_id))[0].kind is IrregularEntryKind.UNPLANNED

    await fund.items.link_payment(fund_id, tx.id, item.id)
    assert (await fund.items.history(fund_id))[0].kind is IrregularEntryKind.PAYMENT

    await fund.items.link_payment(fund_id, tx.id, None)
    assert (await fund.items.history(fund_id))[0].kind is IrregularEntryKind.UNPLANNED


async def test_only_the_funds_own_expenses_and_items_link(fund: _Fund) -> None:
    fund_id, _ = await fund.holding("800.00")
    other_fund, other_account = await fund.holding("100.00")
    cat = await fund.category("Różne")
    foreign_item = await fund.items.create(
        other_fund, IrregularItemCreate(name="Kominiarz", yearly_amount=Decimal("150.00"))
    )
    elsewhere = await TransactionService(fund.session).create(
        TransactionCreate(
            account_id=other_account,
            category_id=cat,
            amount=Decimal("50.00"),
            type=TransactionType.EXPENSE,
            date=DAY,
        )
    )
    with pytest.raises(ValidationError):
        await fund.items.link_payment(fund_id, elsewhere.id, None)
    with pytest.raises(ValidationError):
        await fund.items.record_payment(
            fund_id,
            IrregularPaymentCreate(
                item_id=foreign_item.id, amount=Decimal("10.00"), date=DAY, category_id=cat
            ),
        )
    # An expense needs a category: none given and the item has none.
    with pytest.raises(ValidationError):
        await fund.items.record_payment(
            fund_id, IrregularPaymentCreate(amount=Decimal("10.00"), date=DAY)
        )


async def test_money_in_and_out_and_a_deleted_item(fund: _Fund) -> None:
    fund_id, account_id = await fund.holding("0.00")
    cat = await fund.category("Serwis")
    item = await fund.items.create(
        fund_id, IrregularItemCreate(name="Przegląd auta", yearly_amount=Decimal("1200.00"))
    )
    txs = TransactionService(fund.session)
    for direction, amount in ((TransferDirection.IN, "500.00"), (TransferDirection.OUT, "50.00")):
        await txs.create(
            TransactionCreate(
                account_id=account_id,
                amount=Decimal(amount),
                type=TransactionType.TRANSFER,
                transfer_direction=direction,
                date=DAY,
            )
        )
    paid = await fund.items.record_payment(
        fund_id,
        IrregularPaymentCreate(
            item_id=item.id, amount=Decimal("100.00"), date=DAY, category_id=cat
        ),
    )

    by_id = {e.transaction_id: e for e in await fund.items.history(fund_id)}
    kinds = sorted((e.kind.value, e.amount) for e in by_id.values())
    assert kinds == [
        ("contribution", Decimal("500.00")),
        ("payment", Decimal("-100.00")),
        ("withdrawal", Decimal("-50.00")),
    ]

    # The item goes; its payment stays in the history, now unplanned.
    await fund.items.delete(item.id)
    after = {e.transaction_id: e for e in await fund.items.history(fund_id)}
    assert after[paid.id].kind is IrregularEntryKind.UNPLANNED
    assert after[paid.id].item_name is None
