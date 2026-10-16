# SPDX-License-Identifier: AGPL-3.0-or-later
"""A handful of gifts a household plans across the year."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.gift import Gift
from kaleta.seeders.base import Seeder, row_count


class GiftsSeeder(Seeder):
    key = "gifts"
    icon = "redeem"

    async def count(self, session: AsyncSession) -> int:
        return await row_count(session, Gift)

    async def create(self, session: AsyncSession) -> dict[str, int]:
        # (person, occasion, yearly amount)
        gifts = [
            ("Mama", "Urodziny", "200.00"),
            ("Mama", "Święta", "150.00"),
            ("Tata", "Urodziny", "200.00"),
            ("Kasia", "Imieniny", "120.00"),
            ("Kasia", "Święta", "180.00"),
        ]
        session.add_all(
            Gift(person=person, occasion=occasion, amount=Decimal(amount))
            for person, occasion, amount in gifts
        )
        return {"gifts": len(gifts)}

    async def remove(self, session: AsyncSession) -> None:
        await session.execute(delete(Gift))
