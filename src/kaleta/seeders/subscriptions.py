# SPDX-License-Identifier: AGPL-3.0-or-later
"""The recurring charges the detector would have written down.

A ``Subscription`` is not a planned transaction: it is what the detector
records when it recognises a repeating charge, and it is what the payment
calendar's day sheet lists under "Subscription charges". A seed with none of
them leaves that section — and the Subscriptions panel — empty.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.subscription import Subscription, SubscriptionStatus
from kaleta.seeders.base import Seeder, row_count
from kaleta.seeders.lookups import payees_by_name, subscription_child

#: name, amount, day of month the charge lands on, cadence in days.
_TRACKED = (
    ("iCloud 200 GB", Decimal("12.99"), 14, 30),
    ("Allegro Smart", Decimal("10.75"), 23, 30),
    ("Netflix", Decimal("22.00"), 3, 30),
    ("Spotify", Decimal("23.00"), 7, 30),
)

#: Where a tracked charge's merchant is looked up, when one of ours matches.
_PAYEE_FOR = {"Netflix": "Netflix", "Spotify": "Spotify", "iCloud 200 GB": "iCloud"}


class SubscriptionsSeeder(Seeder):
    key = "subscriptions"
    depends_on = ("taxonomy",)
    icon = "autorenew"

    async def count(self, session: AsyncSession) -> int:
        return await row_count(session, Subscription)

    async def create(self, session: AsyncSession) -> dict[str, int]:
        monthly = await subscription_child(session, "Miesięczne")
        payees = await payees_by_name(session)
        today = datetime.date.today()

        rows: list[Subscription] = []
        for name, amount, day, cadence in _TRACKED:
            next_expected = datetime.date(today.year, today.month, day)
            payee = payees.get(_PAYEE_FOR.get(name, ""))
            rows.append(
                Subscription(
                    name=name,
                    amount=amount,
                    cadence_days=cadence,
                    # Three cadences of history: enough for the detector's own
                    # "seen repeatedly" story to hold on the seeded data.
                    first_seen_at=next_expected - datetime.timedelta(days=cadence * 3),
                    next_expected_at=next_expected,
                    status=SubscriptionStatus.ACTIVE,
                    category_id=monthly.id,
                    payee_id=payee.id if payee is not None else None,
                    auto_renew=True,
                )
            )

        # One cancelled row: the panel's Cancelled filter and the "was this
        # worth keeping?" question both need a row that is no longer running.
        rows.append(
            Subscription(
                name="Magazyn Focus",
                amount=Decimal("19.90"),
                cadence_days=30,
                first_seen_at=today - datetime.timedelta(days=400),
                next_expected_at=None,
                status=SubscriptionStatus.CANCELLED,
                cancelled_at=today - datetime.timedelta(days=45),
                category_id=monthly.id,
                auto_renew=False,
                notes="Zrezygnowano — prenumerata papierowa",
            )
        )
        session.add_all(rows)
        return {"subscriptions": len(rows)}

    async def remove(self, session: AsyncSession) -> None:
        await session.execute(delete(Subscription))
