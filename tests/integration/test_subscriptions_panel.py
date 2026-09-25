# SPDX-License-Identifier: AGPL-3.0-or-later
"""Subscriptions panel — monthly total and cancelling as of a date."""

from __future__ import annotations

import datetime
from decimal import Decimal

from kaleta.models.subscription import SubscriptionStatus
from kaleta.schemas.subscription import SubscriptionCreate
from kaleta.services import SubscriptionService
from tests.conftest import make_session_factory


async def test_monthly_total_counts_a_yearly_bill_as_a_twelfth(db_engine) -> None:
    """Covers: KAL-SUB-002

    Netflix 49.99 monthly + Domain 120.00 yearly shows 59.99 per month
    (120.00 / 12 = 10.00 included).
    """
    async with make_session_factory(db_engine)() as session:
        svc = SubscriptionService(session)
        await svc.create(
            SubscriptionCreate(name="Netflix", amount=Decimal("49.99"), cadence_days=30)
        )
        await svc.create(
            SubscriptionCreate(name="Domain", amount=Decimal("120.00"), cadence_days=365)
        )
        totals = await svc.totals()

    assert totals.monthly_total == Decimal("59.99")


async def test_cancel_as_of_end_of_month(db_engine) -> None:
    """Covers: KAL-SUB-004

    On 2026-04-15 Netflix 49.99 monthly is cancelled as of 2026-04-30: until
    then it stays active and counts 49.99; from 2026-04-30 it is in the
    cancelled section and no longer counts toward the monthly total.
    """
    async with make_session_factory(db_engine)() as session:
        svc = SubscriptionService(session)
        sub = await svc.create(
            SubscriptionCreate(name="Netflix", amount=Decimal("49.99"), cadence_days=30)
        )
        scheduled = await svc.cancel(
            sub.id,
            effective_on=datetime.date(2026, 4, 30),
            today=datetime.date(2026, 4, 15),
        )
        assert scheduled is not None
        assert scheduled.status == SubscriptionStatus.ACTIVE

        assert await svc.settle_due_cancellations(today=datetime.date(2026, 4, 29)) == 0
        before = await svc.totals(today=datetime.date(2026, 4, 29))
        assert before.active_count == 1
        assert before.monthly_total == Decimal("49.99")

        after = await svc.totals(today=datetime.date(2026, 4, 30))
        assert after.active_count == 0
        assert after.monthly_total == Decimal("0.00")

        assert await svc.settle_due_cancellations(today=datetime.date(2026, 4, 30)) == 1
        cancelled = await svc.list(status=SubscriptionStatus.CANCELLED)
        assert [s.name for s in cancelled] == ["Netflix"]
        assert cancelled[0].cancelled_at == datetime.date(2026, 4, 30)
        assert cancelled[0].next_expected_at is None
