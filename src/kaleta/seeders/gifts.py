# SPDX-License-Identifier: AGPL-3.0-or-later
"""A household's gift grid for the current year: three people, six occasions."""

from __future__ import annotations

import datetime
from decimal import Decimal

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.gift import GiftCell, GiftOccasion, GiftPerson
from kaleta.seeders.base import Seeder, row_count

_OCCASIONS = ("Urodziny", "Imieniny", "Boże Narodzenie", "Wielkanoc", "Mikołajki", "Inne")
_PEOPLE = ("Mama", "Tata", "Ania")
# (person, occasion, amount, note)
_CELLS = (
    ("Mama", "Urodziny", "200.00", None),
    ("Mama", "Boże Narodzenie", "150.00", None),
    ("Mama", "Inne", "100.00", "Dzień Matki"),
    ("Tata", "Urodziny", "200.00", None),
    ("Tata", "Boże Narodzenie", "150.00", None),
    ("Ania", "Imieniny", "120.00", None),
    ("Ania", "Boże Narodzenie", "180.00", None),
    ("Ania", "Mikołajki", "50.00", None),
)


class GiftsSeeder(Seeder):
    key = "gifts"
    icon = "redeem"

    async def count(self, session: AsyncSession) -> int:
        return await row_count(session, GiftCell)

    async def create(self, session: AsyncSession) -> dict[str, int]:
        occasions = {name: GiftOccasion(name=name, position=i) for i, name in enumerate(_OCCASIONS)}
        people = {name: GiftPerson(name=name, position=i) for i, name in enumerate(_PEOPLE)}
        session.add_all([*occasions.values(), *people.values()])
        await session.flush()
        year = datetime.date.today().year
        session.add_all(
            GiftCell(
                year=year,
                person_id=people[person].id,
                occasion_id=occasions[occasion].id,
                amount=Decimal(amount),
                note=note,
            )
            for person, occasion, amount, note in _CELLS
        )
        return {"gifts": len(_CELLS)}

    async def remove(self, session: AsyncSession) -> None:
        await session.execute(delete(GiftCell))
        await session.execute(delete(GiftPerson))
        await session.execute(delete(GiftOccasion))
