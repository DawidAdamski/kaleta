# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import builtins
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import NotFoundError
from kaleta.models.gift import Gift
from kaleta.schemas.gift import (
    GiftCreate,
    GiftPersonGroup,
    GiftResponse,
    GiftsSummary,
    GiftUpdate,
)


class GiftService:
    """Planned gifts: per-person entries and the yearly total they sum to."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, payload: GiftCreate) -> Gift:
        gift = Gift(person=payload.person, occasion=payload.occasion, amount=payload.amount)
        self.session.add(gift)
        await self.session.commit()
        await self.session.refresh(gift)
        return gift

    async def get(self, gift_id: int) -> Gift | None:
        result = await self.session.execute(select(Gift).where(Gift.id == gift_id))
        return result.scalar_one_or_none()

    async def list(self) -> builtins.list[Gift]:
        result = await self.session.execute(select(Gift).order_by(Gift.id))
        return list(result.scalars().all())

    async def update(self, gift_id: int, payload: GiftUpdate) -> Gift:
        gift = await self.get(gift_id)
        if gift is None:
            raise NotFoundError(f"Gift {gift_id} not found")
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(gift, key, value)
        await self.session.commit()
        await self.session.refresh(gift)
        return gift

    async def delete(self, gift_id: int) -> None:
        gift = await self.get(gift_id)
        if gift is None:
            raise NotFoundError(f"Gift {gift_id} not found")
        await self.session.delete(gift)
        await self.session.commit()

    async def summary(self) -> GiftsSummary:
        """The list grouped by person (names are encrypted, so group in Python).

        Groups are ordered by person (case-insensitive); gifts within a group
        keep insertion order (by id). The yearly total is the plain sum of every
        gift's amount.
        """
        gifts = await self.list()

        by_person: dict[str, list[GiftResponse]] = {}
        for gift in gifts:
            by_person.setdefault(gift.person, []).append(GiftResponse.model_validate(gift))

        groups = [
            GiftPersonGroup(
                person=person,
                gifts=entries,
                subtotal=sum((g.amount for g in entries), Decimal("0")),
            )
            for person, entries in sorted(by_person.items(), key=lambda kv: kv[0].casefold())
        ]
        yearly_total = sum((group.subtotal for group in groups), Decimal("0"))
        return GiftsSummary(groups=groups, yearly_total=yearly_total)
