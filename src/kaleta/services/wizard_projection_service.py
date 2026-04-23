"""Cross-panel projection layer.

Each wizard panel has a rich UI rooted in its own service. This aggregator
reads every source of truth that other panels produce and projects it into
the shape the consumer panel wants to render — monthly-equivalent amounts
for Budget Builder, per-day subscription charges for Payment Calendar, etc.

No service call here mutates. Pulled rows surface as **read-only** on the
consumer side; the consumer must link back to the source panel for edits.
"""

from __future__ import annotations

import datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.credit import LoanProfile
from kaleta.models.planned_transaction import (
    PlannedTransaction,
    RecurrenceFrequency,
)
from kaleta.models.reserve_fund import ReserveFund, ReserveFundKind
from kaleta.models.subscription import Subscription, SubscriptionStatus
from kaleta.models.transaction import TransactionType
from kaleta.schemas.wizard_projections import (
    BudgetBuilderProjection,
    PaymentCalendarProjection,
    PulledRow,
    SubscriptionCharge,
)

# ── Frequency → monthly equivalent ───────────────────────────────────────────

_MONTHLY_MULTIPLIER: dict[RecurrenceFrequency, Decimal] = {
    RecurrenceFrequency.DAILY: Decimal("30"),
    RecurrenceFrequency.WEEKLY: Decimal("30") / Decimal("7"),
    RecurrenceFrequency.BIWEEKLY: Decimal("30") / Decimal("14"),
    RecurrenceFrequency.MONTHLY: Decimal("1"),
    RecurrenceFrequency.QUARTERLY: Decimal("1") / Decimal("3"),
    RecurrenceFrequency.YEARLY: Decimal("1") / Decimal("12"),
}


def _monthly_from_planned(pt: PlannedTransaction) -> Decimal:
    """Project a recurring planned-transaction's amount onto one month."""
    if pt.frequency == RecurrenceFrequency.ONCE:
        return Decimal("0")  # ONCE has no monthly rate; caller skips these
    multiplier = _MONTHLY_MULTIPLIER.get(pt.frequency, Decimal("1"))
    base = abs(pt.amount) * multiplier
    if pt.interval and pt.interval > 0:
        base = base / Decimal(pt.interval)
    return base.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _monthly_from_subscription(sub: Subscription) -> Decimal:
    """amount × 30 / cadence_days so yearly subs amortise to monthly."""
    if sub.cadence_days <= 0:
        return abs(sub.amount)
    return (
        abs(sub.amount) * Decimal("30") / Decimal(sub.cadence_days)
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _monthly_from_reserve(fund: ReserveFund) -> Decimal:
    """Derive a monthly contribution from target + multiplier.

    Emergency funds with a multiplier use ``target / multiplier`` so the bar
    fills at a rate of one "month of survival" per calendar month. Everything
    else falls back to ``target / 12`` as a conservative annual amortisation.
    """
    target = Decimal(fund.target_amount or 0)
    if target <= 0:
        return Decimal("0")
    if (
        fund.kind == ReserveFundKind.EMERGENCY
        and fund.emergency_multiplier
        and fund.emergency_multiplier >= 1
    ):
        return (target / Decimal(fund.emergency_multiplier)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    return (target / Decimal("12")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def _frequency_label(pt: PlannedTransaction) -> str:
    return pt.frequency.value if pt.interval == 1 else f"every {pt.interval} × {pt.frequency.value}"


def _subscription_cadence_label(sub: Subscription) -> str:
    if 27 <= sub.cadence_days <= 33:
        return "monthly"
    if 350 <= sub.cadence_days <= 380:
        return "yearly"
    return f"{sub.cadence_days}d"


class WizardProjectionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Budget Builder ────────────────────────────────────────────────────

    async def get_budget_builder_sources(
        self, year: int
    ) -> BudgetBuilderProjection:
        """Rows every Budget Builder section should pull in for the given year."""
        projection = BudgetBuilderProjection()

        # Planned transactions — active, non-transfer, filtered by type.
        planned_result = await self.session.execute(
            select(PlannedTransaction)
            .where(PlannedTransaction.is_active.is_(True))
            .order_by(PlannedTransaction.name)
        )
        for pt in planned_result.scalars().all():
            if pt.frequency == RecurrenceFrequency.ONCE:
                continue  # ONCE items are not recurring; skip for monthly view
            if pt.type == TransactionType.TRANSFER:
                continue
            monthly = _monthly_from_planned(pt)
            if monthly <= 0:
                continue
            row = PulledRow(
                source_kind="planned",
                source_id=pt.id,
                label=pt.name,
                amount=monthly,
                cadence=_frequency_label(pt),
                href="/planned",
            )
            if pt.type == TransactionType.INCOME:
                projection.income.append(row)
            else:  # EXPENSE
                projection.fixed.append(row)

        # Active subscriptions — always Fixed.
        subs_result = await self.session.execute(
            select(Subscription).where(
                Subscription.status == SubscriptionStatus.ACTIVE
            )
        )
        for sub in subs_result.scalars().all():
            monthly = _monthly_from_subscription(sub)
            if monthly <= 0:
                continue
            projection.fixed.append(
                PulledRow(
                    source_kind="subscription",
                    source_id=sub.id,
                    label=sub.name,
                    amount=monthly,
                    cadence=_subscription_cadence_label(sub),
                    href="/wizard/subscriptions",
                )
            )

        # Personal-finance loans (amortising) — monthly payment goes in Fixed.
        loans_result = await self.session.execute(select(LoanProfile))
        for loan in loans_result.scalars().all():
            if loan.monthly_payment <= 0:
                continue
            projection.fixed.append(
                PulledRow(
                    source_kind="loan",
                    source_id=loan.account_id,
                    label=f"Loan #{loan.account_id}",
                    amount=loan.monthly_payment,
                    cadence="monthly",
                    href="/credit",
                )
            )

        # Reserve funds — derived monthly contribution.
        funds_result = await self.session.execute(
            select(ReserveFund).where(ReserveFund.is_archived.is_(False))
        )
        for fund in funds_result.scalars().all():
            monthly = _monthly_from_reserve(fund)
            if monthly <= 0:
                continue
            projection.reserves.append(
                PulledRow(
                    source_kind="reserve",
                    source_id=fund.id,
                    label=fund.name,
                    amount=monthly,
                    cadence="monthly (derived)",
                    href="/wizard/safety-funds",
                )
            )

        # Stable, predictable ordering for snapshot-friendly tests.
        projection.income.sort(key=lambda r: (r.label.lower(), r.source_id))
        projection.fixed.sort(
            key=lambda r: (
                {"subscription": 0, "loan": 1, "planned": 2, "reserve": 3}.get(
                    r.source_kind, 9
                ),
                r.label.lower(),
                r.source_id,
            )
        )
        projection.reserves.sort(key=lambda r: (r.label.lower(), r.source_id))
        return projection

    # ── Payment Calendar ──────────────────────────────────────────────────

    async def get_payment_calendar_sources(
        self, start: datetime.date, end: datetime.date
    ) -> PaymentCalendarProjection:
        """Project active subscription charges onto the ``[start, end]`` window."""
        if end < start:
            return PaymentCalendarProjection()

        subs_result = await self.session.execute(
            select(Subscription).where(
                Subscription.status == SubscriptionStatus.ACTIVE
            )
        )
        charges: list[SubscriptionCharge] = []
        for sub in subs_result.scalars().all():
            if sub.cadence_days <= 0:
                continue
            # Walk forward from the earliest known anchor.
            anchor = sub.first_seen_at or sub.next_expected_at
            if anchor is None:
                continue
            cursor = anchor
            # Fast-forward to the window's start.
            while cursor < start:
                cursor = cursor + datetime.timedelta(days=sub.cadence_days)
            while cursor <= end:
                charges.append(
                    SubscriptionCharge(
                        date=cursor,
                        subscription_id=sub.id,
                        name=sub.name,
                        amount=abs(sub.amount),
                    )
                )
                cursor = cursor + datetime.timedelta(days=sub.cadence_days)
        charges.sort(key=lambda c: (c.date, c.name.lower()))
        return PaymentCalendarProjection(subscription_charges=charges)


__all__ = [
    "WizardProjectionService",
]
