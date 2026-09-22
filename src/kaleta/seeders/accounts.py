# SPDX-License-Identifier: AGPL-3.0-or-later
"""The institutions and the four accounts everything else posts to.

Balances are left at zero here. The transactions seeder is the only thing that
knows what the ledger sums to, so it is the only thing that sets them —
otherwise seeding accounts alone would show a balance no rows support.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.account import Account, AccountType
from kaleta.models.institution import Institution, InstitutionType
from kaleta.seeders.base import Seeder, row_count
from kaleta.seeders.catalog import ACCOUNT_NAMES


class AccountsSeeder(Seeder):
    key = "accounts"
    icon = "account_balance"

    async def count(self, session: AsyncSession) -> int:
        return await row_count(session, Account)

    async def create(self, session: AsyncSession) -> dict[str, int]:
        institutions = [
            Institution(
                name="PKO Bank Polski",
                type=InstitutionType.BANK,
                color="#003087",
                website="https://www.pkobp.pl",
                description="Największy bank w Polsce",
            ),
            Institution(
                name="mBank",
                type=InstitutionType.FINTECH,
                color="#e2001a",
                website="https://www.mbank.pl",
                description="Nowoczesny bank internetowy",
            ),
            Institution(
                name="Revolut",
                type=InstitutionType.FINTECH,
                color="#191c1f",
                website="https://www.revolut.com",
                description="Aplikacja finansowa — karty i wymiana walut",
            ),
        ]
        session.add_all(institutions)
        await session.flush()
        pko, mbank, revolut = institutions

        accounts = [
            Account(
                name=ACCOUNT_NAMES["checking"],
                type=AccountType.CHECKING,
                balance=Decimal("0.00"),
                institution_id=pko.id,
            ),
            Account(
                name=ACCOUNT_NAMES["savings"],
                type=AccountType.SAVINGS,
                balance=Decimal("0.00"),
                institution_id=mbank.id,
            ),
            Account(
                name=ACCOUNT_NAMES["cash"],
                type=AccountType.CASH,
                balance=Decimal("0.00"),
            ),
            Account(
                name=ACCOUNT_NAMES["credit"],
                type=AccountType.CREDIT,
                balance=Decimal("0.00"),
                institution_id=revolut.id,
            ),
        ]
        session.add_all(accounts)
        return {"institutions": len(institutions), "accounts": len(accounts)}

    async def remove(self, session: AsyncSession) -> None:
        await session.execute(delete(Account))
        await session.execute(delete(Institution))
