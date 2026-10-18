# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for GiftService."""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import NotFoundError, ValidationError
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.category import CategoryCreate, CategoryType
from kaleta.schemas.gift import GiftCreate, GiftUpdate
from kaleta.schemas.transaction import TransactionCreate, TransactionType
from kaleta.services import (
    AccountService,
    CategoryService,
    GiftService,
    TransactionService,
)


@pytest.fixture
def svc(session: AsyncSession) -> GiftService:
    return GiftService(session)


async def _expense(
    session: AsyncSession, amount: str, *, kind: TransactionType | None = None
) -> int:
    """A standalone transaction (expense unless told otherwise); returns its id."""
    tx_type = kind or TransactionType.EXPENSE
    cat_type = CategoryType.INCOME if tx_type is TransactionType.INCOME else CategoryType.EXPENSE
    account = await AccountService(session).create(
        AccountCreate(name="Konto", balance=Decimal("0.00"))
    )
    category = await CategoryService(session).create(
        CategoryCreate(name=f"Prezenty {amount}", type=cat_type)
    )
    tx = await TransactionService(session).create(
        TransactionCreate(
            account_id=account.id,
            category_id=category.id,
            amount=Decimal(amount),
            type=tx_type,
            date=datetime.date(2026, 6, 1),
            description="Gift purchase",
        )
    )
    return tx.id


class TestGiftServiceCreate:
    async def test_create_returns_gift_with_id(self, svc: GiftService):
        gift = await svc.create(
            GiftCreate(person="Mum", occasion="birthday", amount=Decimal("200.00"))
        )
        assert gift.id is not None
        assert gift.person == "Mum"
        assert gift.occasion == "birthday"
        assert gift.amount == Decimal("200.00")

    async def test_list_orders_by_id(self, svc: GiftService):
        a = await svc.create(GiftCreate(person="Mum", occasion="birthday", amount=Decimal("200")))
        b = await svc.create(GiftCreate(person="Dad", occasion="name day", amount=Decimal("120")))
        ids = [g.id for g in await svc.list()]
        assert ids == [a.id, b.id]


class TestGiftServiceSummary:
    async def test_groups_by_person_and_totals(self, svc: GiftService):
        """Covers: KAL-GFT-001

        Two gifts for "Mum" (200.00 + 150.00) group under one person with a
        350.00 subtotal, and the yearly total is 350.00 — the BDD literals.
        """
        await svc.create(GiftCreate(person="Mum", occasion="birthday", amount=Decimal("200.00")))
        await svc.create(GiftCreate(person="Mum", occasion="Christmas", amount=Decimal("150.00")))

        summary = await svc.summary()

        assert len(summary.groups) == 1
        group = summary.groups[0]
        assert group.person == "Mum"
        assert len(group.gifts) == 2
        assert {g.occasion for g in group.gifts} == {"birthday", "Christmas"}
        assert group.subtotal == Decimal("350.00")
        assert summary.yearly_total == Decimal("350.00")

    async def test_empty_summary_is_zero(self, svc: GiftService):
        summary = await svc.summary()
        assert summary.groups == []
        assert summary.yearly_total == Decimal("0")

    async def test_separate_people_are_separate_groups(self, svc: GiftService):
        await svc.create(GiftCreate(person="Mum", occasion="birthday", amount=Decimal("200.00")))
        await svc.create(GiftCreate(person="Dad", occasion="birthday", amount=Decimal("120.00")))

        summary = await svc.summary()

        assert [g.person for g in summary.groups] == ["Dad", "Mum"]  # sorted, case-insensitive
        assert summary.yearly_total == Decimal("320.00")


class TestGiftServiceUpdateDelete:
    async def test_update_changes_fields(self, svc: GiftService):
        gift = await svc.create(
            GiftCreate(person="Mum", occasion="birthday", amount=Decimal("200.00"))
        )
        updated = await svc.update(gift.id, GiftUpdate(amount=Decimal("250.00")))
        assert updated is not None
        assert updated.amount == Decimal("250.00")
        assert updated.person == "Mum"

    async def test_update_missing_raises_not_found(self, svc: GiftService):
        with pytest.raises(NotFoundError):
            await svc.update(9999, GiftUpdate(amount=Decimal("1")))

    async def test_delete_removes_the_gift(self, svc: GiftService):
        gift = await svc.create(
            GiftCreate(person="Mum", occasion="birthday", amount=Decimal("200.00"))
        )
        await svc.delete(gift.id)
        assert await svc.get(gift.id) is None

    async def test_delete_missing_raises_not_found(self, svc: GiftService):
        with pytest.raises(NotFoundError):
            await svc.delete(9999)


class TestGiftServiceMarkBought:
    async def test_linking_a_transaction_marks_the_gift_bought(
        self, svc: GiftService, session: AsyncSession
    ):
        """Covers: KAL-GFT-003

        A gift planned at 200.00, linked to a 189.99 expense, is marked bought
        with that actual cost — the BDD literals.
        """
        gift = await svc.create(
            GiftCreate(person="Mum", occasion="birthday", amount=Decimal("200.00"))
        )
        tx_id = await _expense(session, "189.99")

        await svc.link_transaction(gift.id, tx_id)

        response = await svc.get_response(gift.id)
        assert response is not None
        assert response.bought is True
        assert response.actual_cost == Decimal("189.99")
        assert response.amount == Decimal("200.00")  # planned amount is untouched

    async def test_unbought_gift_has_no_actual_cost(self, svc: GiftService):
        gift = await svc.create(
            GiftCreate(person="Mum", occasion="birthday", amount=Decimal("200.00"))
        )
        response = await svc.get_response(gift.id)
        assert response is not None
        assert response.bought is False
        assert response.actual_cost is None

    async def test_actual_cost_sums_several_linked_transactions(
        self, svc: GiftService, session: AsyncSession
    ):
        gift = await svc.create(
            GiftCreate(person="Mum", occasion="birthday", amount=Decimal("200.00"))
        )
        await svc.link_transaction(gift.id, await _expense(session, "120.00"))
        await svc.link_transaction(gift.id, await _expense(session, "69.99"))

        response = await svc.get_response(gift.id)
        assert response is not None
        assert response.actual_cost == Decimal("189.99")

    async def test_mark_not_bought_unlinks(self, svc: GiftService, session: AsyncSession):
        gift = await svc.create(
            GiftCreate(person="Mum", occasion="birthday", amount=Decimal("200.00"))
        )
        await svc.link_transaction(gift.id, await _expense(session, "189.99"))

        await svc.mark_not_bought(gift.id)

        response = await svc.get_response(gift.id)
        assert response is not None
        assert response.bought is False
        assert response.actual_cost is None

    async def test_summary_carries_bought_state(self, svc: GiftService, session: AsyncSession):
        gift = await svc.create(
            GiftCreate(person="Mum", occasion="birthday", amount=Decimal("200.00"))
        )
        await svc.link_transaction(gift.id, await _expense(session, "189.99"))

        summary = await svc.summary()
        [entry] = summary.groups[0].gifts
        assert entry.bought is True
        assert entry.actual_cost == Decimal("189.99")

    async def test_cannot_link_a_non_expense(self, svc: GiftService, session: AsyncSession):
        gift = await svc.create(
            GiftCreate(person="Mum", occasion="birthday", amount=Decimal("200.00"))
        )
        income_id = await _expense(session, "189.99", kind=TransactionType.INCOME)
        with pytest.raises(ValidationError):
            await svc.link_transaction(gift.id, income_id)

    async def test_link_missing_gift_raises(self, svc: GiftService, session: AsyncSession):
        tx_id = await _expense(session, "189.99")
        with pytest.raises(NotFoundError):
            await svc.link_transaction(9999, tx_id)

    async def test_link_missing_transaction_raises(self, svc: GiftService):
        gift = await svc.create(
            GiftCreate(person="Mum", occasion="birthday", amount=Decimal("200.00"))
        )
        with pytest.raises(NotFoundError):
            await svc.link_transaction(gift.id, 9999)
