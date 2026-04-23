"""Subscriptions — CRUD, recurring-charge detector, upcoming renewals."""

from __future__ import annotations

import builtins
import datetime
import re
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.dismissed_candidate import DismissedCandidate
from kaleta.models.payee import Payee
from kaleta.models.subscription import Subscription, SubscriptionStatus
from kaleta.models.transaction import Transaction, TransactionType
from kaleta.schemas.subscription import (
    DetectorCandidate,
    RenewalRow,
    SubscriptionCreate,
    SubscriptionTotals,
    SubscriptionUpdate,
)

# Detector tuning ─ start conservative, revisit after dogfood.
# Window = 24 months so yearly subs that last charged up to ~18 mo ago still
# match (need 2 occurrences for a yearly = one in month 0, one ~12 mo later).
DETECTOR_WINDOW_DAYS = 730
CADENCE_MONTHLY_DAYS = 30
CADENCE_YEARLY_DAYS = 365
CADENCE_MONTHLY_TOLERANCE = 5  # ± days (roomier than plan's 3 to absorb weekends)
CADENCE_YEARLY_TOLERANCE = 21
AMOUNT_TOLERANCE_PCT = Decimal("0.05")  # ±5 %
MIN_OCCURRENCES = 2  # need at least 2 charges to call something recurring


class SubscriptionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── CRUD ──────────────────────────────────────────────────────────────

    async def get(self, sub_id: int) -> Subscription | None:
        result = await self.session.execute(
            select(Subscription).where(Subscription.id == sub_id)
        )
        return result.scalar_one_or_none()

    async def list(
        self, *, status: SubscriptionStatus | None = None
    ) -> builtins.list[Subscription]:
        stmt = select(Subscription).order_by(Subscription.name)
        if status is not None:
            stmt = stmt.where(Subscription.status == status)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, payload: SubscriptionCreate) -> Subscription:
        sub = Subscription(
            name=payload.name,
            amount=payload.amount,
            cadence_days=payload.cadence_days,
            payee_id=payload.payee_id,
            category_id=payload.category_id,
            first_seen_at=payload.first_seen_at,
            next_expected_at=payload.next_expected_at
            or _project_next_expected(
                payload.first_seen_at, payload.cadence_days
            ),
            url=payload.url,
            auto_renew=payload.auto_renew,
            status=SubscriptionStatus.ACTIVE,
        )
        self.session.add(sub)
        await self.session.commit()
        await self.session.refresh(sub)
        return sub

    async def update(
        self, sub_id: int, payload: SubscriptionUpdate
    ) -> Subscription | None:
        sub = await self.get(sub_id)
        if sub is None:
            return None
        data = payload.model_dump(exclude_unset=True)
        for key, value in data.items():
            setattr(sub, key, value)
        await self.session.commit()
        await self.session.refresh(sub)
        return sub

    async def delete(self, sub_id: int) -> bool:
        sub = await self.get(sub_id)
        if sub is None:
            return False
        await self.session.delete(sub)
        await self.session.commit()
        return True

    async def mute_one_cycle(
        self, sub_id: int, *, today: datetime.date | None = None
    ) -> Subscription | None:
        sub = await self.get(sub_id)
        if sub is None:
            return None
        ref = today or datetime.date.today()
        muted_until = ref + datetime.timedelta(days=sub.cadence_days)
        sub.status = SubscriptionStatus.MUTED
        sub.muted_until = muted_until
        await self.session.commit()
        await self.session.refresh(sub)
        return sub

    async def cancel(
        self, sub_id: int, *, today: datetime.date | None = None
    ) -> Subscription | None:
        sub = await self.get(sub_id)
        if sub is None:
            return None
        ref = today or datetime.date.today()
        sub.status = SubscriptionStatus.CANCELLED
        sub.cancelled_at = ref
        sub.next_expected_at = None
        await self.session.commit()
        await self.session.refresh(sub)
        return sub

    async def reactivate(self, sub_id: int) -> Subscription | None:
        sub = await self.get(sub_id)
        if sub is None:
            return None
        sub.status = SubscriptionStatus.ACTIVE
        sub.muted_until = None
        sub.cancelled_at = None
        if sub.first_seen_at:
            sub.next_expected_at = _project_next_expected(
                sub.first_seen_at, sub.cadence_days
            )
        await self.session.commit()
        await self.session.refresh(sub)
        return sub

    # ── Detector ──────────────────────────────────────────────────────────

    async def detect_candidates(
        self,
        *,
        today: datetime.date | None = None,
        window_days: int | None = None,
    ) -> builtins.list[DetectorCandidate]:
        ref = today or datetime.date.today()
        effective_window = window_days if window_days and window_days > 0 else DETECTOR_WINDOW_DAYS
        window_start = ref - datetime.timedelta(days=effective_window)

        # Existing subscriptions block their payees/names from candidates.
        existing = await self.session.execute(
            select(Subscription.payee_id, Subscription.name).where(
                Subscription.status != SubscriptionStatus.CANCELLED,
            )
        )
        tracked_payee_ids: set[int] = set()
        tracked_merchant_keys: set[str] = set()
        for payee_id, name in existing.all():
            if payee_id is not None:
                tracked_payee_ids.add(payee_id)
            if name:
                tracked_merchant_keys.add(_merchant_key_from_description(name))

        # Dismissed patterns — user previously clicked "not a subscription".
        dismissed_result = await self.session.execute(
            select(
                DismissedCandidate.payee_id,
                DismissedCandidate.merchant_key,
                DismissedCandidate.amount_bucket,
            )
        )
        dismissed_by_payee: set[tuple[int, str]] = set()
        dismissed_by_key: set[tuple[str, str]] = set()
        for d_payee_id, d_merchant_key, d_bucket in dismissed_result.all():
            if d_payee_id is not None:
                dismissed_by_payee.add((d_payee_id, d_bucket))
            elif d_merchant_key is not None:
                dismissed_by_key.add((d_merchant_key, d_bucket))

        # ── PASS 1: rows with a Payee ──────────────────────────────────────
        payee_rows = await self.session.execute(
            select(Transaction, Payee)
            .join(Payee, Transaction.payee_id == Payee.id)
            .where(
                Transaction.type == TransactionType.EXPENSE,
                Transaction.is_internal_transfer == False,  # noqa: E712
                Transaction.date >= window_start,
                Transaction.date <= ref,
            )
            .order_by(Transaction.date)
        )
        pass1_groups: dict[tuple[int, str], list[Transaction]] = defaultdict(list)
        payee_names: dict[int, str] = {}
        for tx, payee in payee_rows.all():
            if payee.id in tracked_payee_ids:
                continue
            bucket = _amount_bucket(abs(tx.amount))
            if (payee.id, bucket) in dismissed_by_payee:
                continue
            pass1_groups[(payee.id, bucket)].append(tx)
            payee_names[payee.id] = payee.name

        candidates: list[DetectorCandidate] = []
        for (payee_id, _bucket), txs in pass1_groups.items():
            candidate = _candidate_from_group(
                txs, name=payee_names[payee_id], payee_id=payee_id
            )
            if candidate is not None:
                candidates.append(candidate)

        # ── PASS 2: rows without a Payee — group by description-key ────────
        # Many imported rows (HBO, Disney Plus, APPLE.COM/BILL, AMAZON.PL)
        # never get a Payee row created for them, so pass 1 misses them.
        orphan_rows = await self.session.execute(
            select(Transaction)
            .where(
                Transaction.type == TransactionType.EXPENSE,
                Transaction.is_internal_transfer == False,  # noqa: E712
                Transaction.payee_id.is_(None),
                Transaction.date >= window_start,
                Transaction.date <= ref,
            )
            .order_by(Transaction.date)
        )
        pass2_groups: dict[tuple[str, str], list[Transaction]] = defaultdict(list)
        for tx in orphan_rows.scalars().all():
            key = _merchant_key_from_description(tx.description)
            if not key:
                continue
            if key in tracked_merchant_keys:
                continue
            bucket = _amount_bucket(abs(tx.amount))
            if (key, bucket) in dismissed_by_key:
                continue
            pass2_groups[(key, bucket)].append(tx)

        for (merchant_key, _bucket), txs in pass2_groups.items():
            candidate = _candidate_from_group(txs, name=merchant_key, payee_id=None)
            if candidate is not None:
                candidates.append(candidate)

        candidates.sort(key=lambda c: c.amount, reverse=True)
        return candidates

    async def dismiss_candidate(self, candidate: DetectorCandidate) -> None:
        """Persist a 'not a subscription' decision so it doesn't resurface."""
        bucket = _amount_bucket(candidate.amount)
        merchant_key = (
            None if candidate.payee_id is not None else candidate.payee_name
        )
        existing = await self.session.execute(
            select(DismissedCandidate).where(
                DismissedCandidate.payee_id == candidate.payee_id,
                DismissedCandidate.merchant_key == merchant_key,
                DismissedCandidate.amount_bucket == bucket,
            )
        )
        if existing.scalar_one_or_none() is not None:
            return
        self.session.add(
            DismissedCandidate(
                payee_id=candidate.payee_id,
                merchant_key=merchant_key,
                amount_bucket=bucket,
            )
        )
        await self.session.commit()

    async def list_dismissed(self) -> builtins.list[DismissedCandidate]:
        result = await self.session.execute(
            select(DismissedCandidate).order_by(DismissedCandidate.id)
        )
        return list(result.scalars().all())

    async def undismiss(self, dismissed_id: int) -> bool:
        result = await self.session.execute(
            select(DismissedCandidate).where(DismissedCandidate.id == dismissed_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return False
        await self.session.delete(row)
        await self.session.commit()
        return True

    async def create_from_candidate(
        self, candidate: DetectorCandidate
    ) -> Subscription:
        # The candidate's next_expected_at is "last seen + cadence". If that's
        # already in the past (irregular history, detector ran today), keep
        # walking forward so the new subscription shows up in Upcoming Renewals.
        next_expected = candidate.next_expected_at
        today = datetime.date.today()
        while next_expected <= today:
            next_expected = next_expected + datetime.timedelta(
                days=candidate.cadence_days
            )
        payload = SubscriptionCreate(
            name=candidate.payee_name,
            amount=candidate.amount,
            cadence_days=candidate.cadence_days,
            payee_id=candidate.payee_id,
            first_seen_at=candidate.first_seen_at,
            next_expected_at=next_expected,
        )
        return await self.create(payload)

    # ── Renewals ──────────────────────────────────────────────────────────

    async def upcoming_renewals(
        self,
        *,
        days: int = 30,
        today: datetime.date | None = None,
    ) -> builtins.list[RenewalRow]:
        ref = today or datetime.date.today()
        deadline = ref + datetime.timedelta(days=days)
        result = await self.session.execute(
            select(Subscription)
            .where(
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.next_expected_at.is_not(None),
                Subscription.next_expected_at >= ref,
                Subscription.next_expected_at <= deadline,
            )
            .order_by(Subscription.next_expected_at)
        )
        subs = list(result.scalars().all())
        return [
            RenewalRow(
                subscription_id=s.id,
                name=s.name,
                amount=s.amount,
                expected_at=s.next_expected_at,  # type: ignore[arg-type]
                days_away=(s.next_expected_at - ref).days,  # type: ignore[operator]
            )
            for s in subs
        ]

    # ── Totals ────────────────────────────────────────────────────────────

    async def totals(self) -> SubscriptionTotals:
        active = await self.list(status=SubscriptionStatus.ACTIVE)
        monthly = Decimal("0.00")
        for s in active:
            monthly += _to_monthly(s.amount, s.cadence_days)
        return SubscriptionTotals(
            active_count=len(active),
            monthly_total=monthly.quantize(Decimal("0.01")),
            yearly_total=(monthly * 12).quantize(Decimal("0.01")),
        )


# ── Helpers ──────────────────────────────────────────────────────────────


def _amount_bucket(amount: Decimal) -> str:
    """Rough bucket for grouping amounts. Tight buckets → merged later."""
    # Round to the nearest 1 PLN; the ±5 % tolerance absorbs fine-grain drift.
    return str(int(round(float(amount))))


# Strip a trailing location/detail suffix so rows for the same service cluster.
# Tuned from live mBank data: "APPLE.COM/BILL /APPLE.COM/", "HBO Europe S.R.O
# /Prague", "Disney Plus /Hoofddorp", "GOOGLE *YouTube Vid/g.co/helpp".
_MERCHANT_KEY_MAX_LEN = 40


def _merchant_key_from_description(desc: str | None) -> str:
    """Normalise a transaction description to a stable merchant-key.

    Keeps the first ``/``-delimited segment (service name before location),
    uppercases, collapses whitespace, and caps length. Returns ``""`` when
    nothing usable remains.
    """
    if not desc:
        return ""
    first = desc.split("/", 1)[0]
    first = re.sub(r"\s+", " ", first).strip().upper()
    return first[:_MERCHANT_KEY_MAX_LEN]


def _candidate_from_group(
    txs: builtins.list[Transaction], *, name: str, payee_id: int | None
) -> DetectorCandidate | None:
    """Return a DetectorCandidate if the tx group is a plausible subscription."""
    if len(txs) < MIN_OCCURRENCES:
        return None
    dates = sorted(tx.date for tx in txs)
    cadence = _infer_cadence(dates)
    if cadence is None:
        return None
    amount_median = _median([abs(tx.amount) for tx in txs])
    return DetectorCandidate(
        payee_id=payee_id,
        payee_name=name,
        amount=amount_median,
        cadence_days=cadence,
        occurrences=len(txs),
        first_seen_at=dates[0],
        last_seen_at=dates[-1],
        next_expected_at=dates[-1] + datetime.timedelta(days=cadence),
    )


def _median(values: builtins.list[Decimal]) -> Decimal:
    s = sorted(values)
    n = len(s)
    if n == 0:
        return Decimal("0")
    mid = n // 2
    if n % 2 == 1:
        return s[mid]
    return ((s[mid - 1] + s[mid]) / 2).quantize(Decimal("0.01"))


def _infer_cadence(dates: builtins.list[datetime.date]) -> int | None:
    """Return 30 (monthly) or 365 (yearly) when the gaps match; else None."""
    if len(dates) < 2:
        return None
    gaps = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))]
    avg = sum(gaps) / len(gaps)

    if abs(avg - CADENCE_MONTHLY_DAYS) <= CADENCE_MONTHLY_TOLERANCE:
        return CADENCE_MONTHLY_DAYS
    if abs(avg - CADENCE_YEARLY_DAYS) <= CADENCE_YEARLY_TOLERANCE:
        return CADENCE_YEARLY_DAYS
    return None


def _project_next_expected(
    first_seen_at: datetime.date | None, cadence_days: int
) -> datetime.date | None:
    if first_seen_at is None:
        return None
    today = datetime.date.today()
    # Walk forward from first_seen_at until next_expected_at > today.
    next_date = first_seen_at
    while next_date <= today:
        next_date = next_date + datetime.timedelta(days=cadence_days)
    return next_date


def _to_monthly(amount: Decimal, cadence_days: int) -> Decimal:
    """Normalise a recurring charge to a monthly equivalent."""
    if cadence_days <= 0:
        return Decimal("0")
    return amount * Decimal(30) / Decimal(cadence_days)


__all__ = ["SubscriptionService"]
