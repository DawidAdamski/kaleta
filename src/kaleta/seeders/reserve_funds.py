# SPDX-License-Identifier: AGPL-3.0-or-later
"""The three funds a household actually keeps.

One emergency fund with a months-of-coverage target, one for the bills that
arrive once a year, and one saving towards something. All three are backed by
the savings account, which is where the balance behind them comes from.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.reserve_fund import ReserveFund, ReserveFundBackingMode, ReserveFundKind
from kaleta.seeders.base import Seeder, row_count
from kaleta.seeders.lookups import accounts_by_kind


class ReserveFundsSeeder(Seeder):
    key = "reserve_funds"
    depends_on = ("accounts",)
    icon = "shield"

    async def count(self, session: AsyncSession) -> int:
        return await row_count(session, ReserveFund)

    async def create(self, session: AsyncSession) -> dict[str, int]:
        savings = (await accounts_by_kind(session))["savings"]
        funds = [
            ReserveFund(
                name="Poduszka bezpieczeństwa",
                kind=ReserveFundKind.EMERGENCY,
                # Six months of the seeded outgoings, rounded to a figure a
                # person would actually write down.
                target_amount=Decimal("30000.00"),
                backing_mode=ReserveFundBackingMode.ACCOUNT,
                backing_account_id=savings.id,
                emergency_multiplier=6,
            ),
            ReserveFund(
                name="Wydatki nieregularne",
                kind=ReserveFundKind.IRREGULAR,
                target_amount=Decimal("7200.00"),
                backing_mode=ReserveFundBackingMode.ACCOUNT,
                backing_account_id=savings.id,
            ),
            ReserveFund(
                name="Wakacje 2027",
                kind=ReserveFundKind.VACATION,
                target_amount=Decimal("9000.00"),
                backing_mode=ReserveFundBackingMode.ACCOUNT,
                backing_account_id=savings.id,
            ),
        ]
        session.add_all(funds)
        return {"reserve_funds": len(funds)}

    async def remove(self, session: AsyncSession) -> None:
        await session.execute(delete(ReserveFund))
