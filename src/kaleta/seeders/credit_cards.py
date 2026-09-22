# SPDX-License-Identifier: AGPL-3.0-or-later
"""The card terms behind the credit account.

The account already carries the balance; what the Credit page needs on top is
the contract — the limit the balance is a share of, the statement and due days
the calendar counts from, and the minimum payment it warns about.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.credit import CreditCardProfile
from kaleta.seeders.base import Seeder, row_count
from kaleta.seeders.lookups import accounts_by_kind


class CreditCardsSeeder(Seeder):
    key = "credit_cards"
    depends_on = ("accounts",)
    icon = "credit_card"

    async def count(self, session: AsyncSession) -> int:
        return await row_count(session, CreditCardProfile)

    async def create(self, session: AsyncSession) -> dict[str, int]:
        credit = (await accounts_by_kind(session))["credit"]
        session.add(
            CreditCardProfile(
                account_id=credit.id,
                credit_limit=Decimal("12000.00"),
                statement_day=5,
                payment_due_day=25,
                min_payment_pct=Decimal("0.0300"),
                min_payment_floor=Decimal("50.00"),
                apr=Decimal("18.99"),
            )
        )
        return {"credit_card_profiles": 1}

    async def remove(self, session: AsyncSession) -> None:
        await session.execute(delete(CreditCardProfile))
