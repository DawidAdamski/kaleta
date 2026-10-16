# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for GiftService."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.schemas.gift import GiftCreate, GiftUpdate
from kaleta.services import GiftService


@pytest.fixture
def svc(session: AsyncSession) -> GiftService:
    return GiftService(session)


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

    async def test_update_missing_returns_none(self, svc: GiftService):
        assert await svc.update(9999, GiftUpdate(amount=Decimal("1"))) is None

    async def test_delete_removes_the_gift(self, svc: GiftService):
        gift = await svc.create(
            GiftCreate(person="Mum", occasion="birthday", amount=Decimal("200.00"))
        )
        assert await svc.delete(gift.id) is True
        assert await svc.get(gift.id) is None

    async def test_delete_missing_returns_false(self, svc: GiftService):
        assert await svc.delete(9999) is False
