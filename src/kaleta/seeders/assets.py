# SPDX-License-Identifier: AGPL-3.0-or-later
"""The things worth money that are not in a bank account.

Net worth is accounts plus assets minus liabilities; a seed with no assets
shows the accounts half of that and makes the split look broken.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.asset import Asset, AssetType
from kaleta.seeders.base import Seeder, row_count


class AssetsSeeder(Seeder):
    key = "assets"
    icon = "home_work"

    async def count(self, session: AsyncSession) -> int:
        return await row_count(session, Asset)

    async def create(self, session: AsyncSession) -> dict[str, int]:
        assets = [
            Asset(
                name="Mieszkanie (Warszawa)",
                type=AssetType.REAL_ESTATE,
                value=Decimal("620000.00"),
                description="Mieszkanie 52m² na Mokotowie, zakupione w 2021",
                purchase_date=datetime.date(2021, 6, 15),
                purchase_price=Decimal("480000.00"),
            ),
            Asset(
                name="Toyota Corolla 2020",
                type=AssetType.VEHICLE,
                value=Decimal("68000.00"),
                description="Toyota Corolla Hybrid 1.8, rok 2020, przebieg 55k km",
                purchase_date=datetime.date(2020, 3, 10),
                purchase_price=Decimal("95000.00"),
            ),
            Asset(
                name="Zegarek Seiko",
                type=AssetType.VALUABLES,
                value=Decimal("4500.00"),
                description="Seiko Prospex, edycja limitowana",
            ),
        ]
        session.add_all(assets)
        return {"assets": len(assets)}

    async def remove(self, session: AsyncSession) -> None:
        await session.execute(delete(Asset))
