# SPDX-License-Identifier: AGPL-3.0-or-later
"""``audit_log.timestamp`` and ``personal_loans.settled_at`` are ``timestamptz``.

Both were the last family timestamps held as ``timestamp without time zone``.
The proof that the column — not just the in-session Python object — is now
tz-aware is to expire the row and reload it from Postgres: asyncpg hands back a
naive ``datetime`` from a naive column and an aware one from ``timestamptz``, so
a reloaded value whose ``tzinfo`` is set can only have come from a ``timestamptz``
column.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.audit_log import AuditLog
from kaleta.models.personal_loan import LoanDirection, LoanStatus, PersonalLoan
from kaleta.schemas.personal_loan import (
    CounterpartyCreate,
    PersonalLoanCreate,
    RepaymentCreate,
)
from kaleta.services import PersonalLoanService


async def test_audit_log_timestamp_reloads_tz_aware(session: AsyncSession) -> None:
    entry = AuditLog(operation="INSERT", table_name="accounts", record_id=1)
    session.add(entry)
    await session.flush()
    entry_id = entry.id

    # Drop the Python object's cached value; the next read comes from Postgres.
    session.expire_all()
    reloaded = (await session.execute(select(AuditLog).where(AuditLog.id == entry_id))).scalar_one()
    assert reloaded.timestamp.tzinfo is not None


async def test_settled_at_reloads_tz_aware(session: AsyncSession) -> None:
    svc = PersonalLoanService(session)
    cp = await svc.create_counterparty(CounterpartyCreate(name="Tomasz"))
    loan = await svc.create_loan(
        PersonalLoanCreate(
            counterparty_id=cp.id,
            direction=LoanDirection.OUTGOING,
            principal=Decimal("500"),
            opened_at=datetime.date(2026, 4, 1),
        )
    )
    # Repay the whole principal: the service flips the loan to SETTLED and
    # stamps ``settled_at`` with an aware UTC ``now()``.
    loan_id = loan.id
    await svc.record_repayment(
        loan_id, RepaymentCreate(amount=Decimal("500"), date=datetime.date(2026, 4, 10))
    )
    await session.flush()

    session.expire_all()
    result = await session.execute(select(PersonalLoan).where(PersonalLoan.id == loan_id))
    reloaded = result.scalar_one()
    assert reloaded.status == LoanStatus.SETTLED
    assert reloaded.settled_at is not None
    assert reloaded.settled_at.tzinfo is not None
