# SPDX-License-Identifier: AGPL-3.0-or-later
"""Money lent and borrowed outside the bank ledger.

Three loans, because the Debt page has three states to show: one outstanding
and partly repaid, one the user owes rather than is owed, and one already
settled. A seed with only the first leaves two thirds of the page unseen.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.personal_loan import (
    Counterparty,
    LoanDirection,
    LoanStatus,
    PersonalLoan,
    PersonalLoanRepayment,
)
from kaleta.seeders.base import Seeder, row_count


class PersonalLoansSeeder(Seeder):
    key = "personal_loans"
    icon = "handshake"

    async def count(self, session: AsyncSession) -> int:
        return await row_count(session, PersonalLoan)

    async def create(self, session: AsyncSession) -> dict[str, int]:
        today = datetime.date.today()
        people = [
            Counterparty(name="Marek Zieliński", notes="Kolega z pracy"),
            Counterparty(name="Anna Kowalczyk", notes="Siostra"),
            Counterparty(name="Tomasz Nowicki"),
        ]
        session.add_all(people)
        await session.flush()
        marek, anna, tomasz = people

        outstanding = PersonalLoan(
            counterparty_id=marek.id,
            direction=LoanDirection.OUTGOING,
            principal=Decimal("2000.00"),
            currency="PLN",
            opened_at=today - datetime.timedelta(days=120),
            due_at=today + datetime.timedelta(days=60),
            notes="Pożyczka na remont — spłata w ratach",
            status=LoanStatus.OUTSTANDING,
        )
        borrowed = PersonalLoan(
            counterparty_id=anna.id,
            direction=LoanDirection.INCOMING,
            principal=Decimal("1500.00"),
            currency="PLN",
            opened_at=today - datetime.timedelta(days=45),
            due_at=today + datetime.timedelta(days=15),
            notes="Dopłata do wyjazdu — oddać po premii",
            status=LoanStatus.OUTSTANDING,
        )
        settled = PersonalLoan(
            counterparty_id=tomasz.id,
            direction=LoanDirection.OUTGOING,
            principal=Decimal("400.00"),
            currency="PLN",
            opened_at=today - datetime.timedelta(days=300),
            due_at=today - datetime.timedelta(days=240),
            status=LoanStatus.SETTLED,
            settled_at=datetime.datetime.combine(
                today - datetime.timedelta(days=250), datetime.time()
            ),
        )
        session.add_all([outstanding, borrowed, settled])
        await session.flush()

        repayments = [
            PersonalLoanRepayment(
                loan_id=outstanding.id,
                amount=Decimal("500.00"),
                date=today - datetime.timedelta(days=90),
                note="Pierwsza rata",
            ),
            PersonalLoanRepayment(
                loan_id=outstanding.id,
                amount=Decimal("500.00"),
                date=today - datetime.timedelta(days=30),
                note="Druga rata",
            ),
            PersonalLoanRepayment(
                loan_id=settled.id,
                amount=Decimal("400.00"),
                date=today - datetime.timedelta(days=250),
                note="Zwrot w całości",
            ),
        ]
        session.add_all(repayments)
        return {
            "counterparties": len(people),
            "personal_loans": 3,
            "personal_loan_repayments": len(repayments),
        }

    async def remove(self, session: AsyncSession) -> None:
        await session.execute(delete(PersonalLoanRepayment))
        await session.execute(delete(PersonalLoan))
        await session.execute(delete(Counterparty))
