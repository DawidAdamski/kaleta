# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unplanned-expenses radar — irregular costs that are likely to repeat.

The subscription detector answers "what charges me every month?". This one
answers the harder question: "what hit me last spring that will hit me again
this spring?" — car service, dentist, school fees, insurance top-ups. Those
repeat every few months to a few years, drift in amount, and surprise the
user because nothing surfaces them ahead of time.

Detection is deliberately conservative: two occurrences at least two months
apart, no more than ~15 months apart, with amounts within ±30 % of the
median. Anything already covered by a planned transaction, an active
subscription, the Subscriptions category tree, or an earlier dismissal is
filtered out.
"""

from __future__ import annotations

import builtins
import datetime
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import NotFoundError, ValidationError
from kaleta.models.category import Category
from kaleta.models.dismissed_candidate import DismissedCandidate, DismissedCandidateKind
from kaleta.models.payee import Payee
from kaleta.models.planned_transaction import PlannedTransaction, RecurrenceFrequency
from kaleta.models.subscription import Subscription, SubscriptionStatus
from kaleta.models.transaction import Transaction, TransactionType
from kaleta.schemas.planned_transaction import PlannedTransactionCreate
from kaleta.schemas.unplanned_radar import RadarCandidate, RadarPlannedRow, RadarSummary
from kaleta.services.planned_transaction_service import PlannedTransactionService
from kaleta.services.subscription_service import merchant_key_from_description

logger = logging.getLogger(__name__)

# ── Detector tuning ──────────────────────────────────────────────────────────
# Three years of history: a yearly cost needs two occurrences ~12 months
# apart, and we want room for one that last fired 18 months ago.
RADAR_WINDOW_DAYS = 1095
# Two occurrences is the floor for calling anything a pattern (plan default).
MIN_OCCURRENCES = 2
# Gaps below this belong to the subscription detector, not here.
MIN_GAP_DAYS = 60
# Beyond ~15 months two expenses are a coincidence, not a rhythm.
MAX_GAP_DAYS = 450
# Irregular costs drift far more than subscriptions do.
AMOUNT_TOLERANCE_PCT = Decimal("0.30")
# Above this average gap we call the rhythm yearly rather than "every N months".
YEARLY_GAP_FLOOR_DAYS = 300
DAYS_PER_YEAR = Decimal("365")

_CENTS = Decimal("0.01")


@dataclass(frozen=True)
class _Occurrence:
    """One historical charge feeding a candidate."""

    transaction_id: int
    date: datetime.date
    amount: Decimal
    account_id: int
    category_id: int | None


def summarise(candidates: builtins.list[RadarCandidate]) -> RadarSummary:
    """Roll candidates up into the irregular-fund suggestion line."""
    yearly = sum((c.yearly_estimate for c in candidates), Decimal("0"))
    yearly = yearly.quantize(_CENTS, rounding=ROUND_HALF_UP)
    monthly = (yearly / Decimal(12)).quantize(_CENTS, rounding=ROUND_HALF_UP)
    return RadarSummary(
        candidate_count=len(candidates),
        yearly_total=yearly,
        monthly_equivalent=monthly,
    )


class UnplannedRadarService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Detection ─────────────────────────────────────────────────────────

    async def detect(
        self,
        *,
        today: datetime.date | None = None,
        window_days: int | None = None,
    ) -> builtins.list[RadarCandidate]:
        """Return irregular repeat-costs worth planning, biggest yearly cost first."""
        ref = today or datetime.date.today()
        effective_window = window_days if window_days and window_days > 0 else RADAR_WINDOW_DAYS
        window_start = ref - datetime.timedelta(days=effective_window)

        excluded_category_ids = await self._subscription_category_ids()
        tracked_payee_ids, tracked_keys = await self._tracked_sources()
        dismissed_payee_ids, dismissed_keys = await self._dismissed_sources()

        stmt = (
            select(Transaction, Payee)
            .outerjoin(Payee, Transaction.payee_id == Payee.id)
            .where(
                Transaction.type == TransactionType.EXPENSE,
                Transaction.is_internal_transfer == False,  # noqa: E712
                Transaction.date >= window_start,
                Transaction.date <= ref,
            )
            .order_by(Transaction.date)
        )
        if excluded_category_ids:
            stmt = stmt.where(
                Transaction.category_id.is_(None)
                | Transaction.category_id.not_in(excluded_category_ids)
            )

        rows = await self.session.execute(stmt)
        by_payee: dict[int, list[_Occurrence]] = defaultdict(list)
        by_key: dict[str, list[_Occurrence]] = defaultdict(list)
        payee_names: dict[int, str] = {}

        for tx, payee in rows.all():
            occ = _Occurrence(
                transaction_id=tx.id,
                date=tx.date,
                amount=abs(tx.amount),
                account_id=tx.account_id,
                category_id=tx.category_id,
            )
            if payee is not None:
                if payee.id in tracked_payee_ids or payee.id in dismissed_payee_ids:
                    continue
                if merchant_key_from_description(payee.name) in tracked_keys:
                    continue
                payee_names[payee.id] = payee.name
                by_payee[payee.id].append(occ)
                continue
            key = merchant_key_from_description(tx.description)
            if not key or key in tracked_keys or key in dismissed_keys:
                continue
            by_key[key].append(occ)

        candidates: builtins.list[RadarCandidate] = []
        for payee_id, occurrences in by_payee.items():
            candidate = _candidate_from_occurrences(
                occurrences, name=payee_names[payee_id], payee_id=payee_id
            )
            if candidate is not None:
                candidates.append(candidate)
        for key, occurrences in by_key.items():
            candidate = _candidate_from_occurrences(occurrences, name=key, payee_id=None)
            if candidate is not None:
                candidates.append(candidate)

        candidates.sort(key=lambda c: (-c.yearly_estimate, c.source_name))
        logger.debug("Radar detected %s irregular candidate(s)", len(candidates))
        return candidates

    # ── Dismissal ─────────────────────────────────────────────────────────

    async def dismiss(self, candidate: RadarCandidate) -> None:
        """Persist "this is not a repeating cost" so it stops resurfacing."""
        bucket = _amount_bucket(candidate.typical_amount)
        merchant_key = None if candidate.payee_id is not None else candidate.source_name
        existing = await self.session.execute(
            select(DismissedCandidate).where(
                DismissedCandidate.payee_id == candidate.payee_id,
                DismissedCandidate.merchant_key == merchant_key,
                DismissedCandidate.amount_bucket == bucket,
                DismissedCandidate.kind == DismissedCandidateKind.UNPLANNED,
            )
        )
        if existing.scalar_one_or_none() is not None:
            return
        self.session.add(
            DismissedCandidate(
                payee_id=candidate.payee_id,
                merchant_key=merchant_key,
                amount_bucket=bucket,
                kind=DismissedCandidateKind.UNPLANNED,
            )
        )
        await self.session.commit()

    # ── Conversion ────────────────────────────────────────────────────────

    async def create_planned_from_candidate(
        self,
        candidate: RadarCandidate,
        *,
        account_id: int | None = None,
        category_id: int | None = None,
        amount: Decimal | None = None,
        start_date: datetime.date | None = None,
        name: str | None = None,
    ) -> PlannedTransaction:
        """Create the planned transaction and link the charges that produced it.

        The historical charges keep pointing at the new plan
        (``Transaction.planned_transaction_id``) so the plan carries its own
        evidence trail.
        """
        planned_name = (name or candidate.source_name).strip()[:100]
        if not planned_name:
            raise ValidationError("A planned transaction needs a name")
        planned_amount = amount if amount is not None else candidate.typical_amount
        if planned_amount <= 0:
            raise ValidationError("A planned transaction needs a positive amount")

        payload = PlannedTransactionCreate(
            name=planned_name,
            amount=planned_amount.quantize(_CENTS, rounding=ROUND_HALF_UP),
            type=TransactionType.EXPENSE,
            account_id=account_id if account_id is not None else candidate.account_id,
            category_id=category_id if category_id is not None else candidate.category_id,
            frequency=candidate.frequency,
            interval=candidate.interval,
            start_date=start_date or candidate.next_expected_at,
        )
        planned = await PlannedTransactionService(self.session).create(payload)
        await self._link_history(planned, candidate)
        await self.session.commit()
        logger.info(
            "Radar converted %r into planned transaction %s",
            candidate.source_name,
            planned.id,
        )
        return planned

    async def _link_history(self, planned: PlannedTransaction, candidate: RadarCandidate) -> None:
        """Point the candidate's source charges at the freshly created plan.

        ``(planned_transaction_id, date)`` is unique, so at most one charge per
        date is linked; the rest keep their existing link (or none).
        """
        if not candidate.transaction_ids:
            return
        result = await self.session.execute(
            select(Transaction)
            .where(
                Transaction.id.in_(candidate.transaction_ids),
                Transaction.planned_transaction_id.is_(None),
            )
            .order_by(Transaction.date)
        )
        seen_dates: set[datetime.date] = set()
        for tx in result.scalars().all():
            if tx.date in seen_dates:
                continue
            seen_dates.add(tx.date)
            tx.planned_transaction_id = planned.id

    # ── Converted plans ───────────────────────────────────────────────────

    async def planned_with_history(self) -> builtins.list[RadarPlannedRow]:
        """Plans that carry linked charges predating them.

        A charge dated before its plan's ``start_date`` is history rather than
        a posted occurrence, which is exactly what conversion leaves behind.
        Nothing marks the link as the radar's, so a hand-linked charge shows
        up here too — the page names the section for what it lists.
        """
        result = await self.session.execute(
            select(Transaction.planned_transaction_id, Transaction.date, PlannedTransaction)
            .join(
                PlannedTransaction,
                Transaction.planned_transaction_id == PlannedTransaction.id,
            )
            .where(Transaction.date < PlannedTransaction.start_date)
            .order_by(PlannedTransaction.name, Transaction.date)
        )
        rows: dict[int, RadarPlannedRow] = {}
        for planned_id, tx_date, planned in result.all():
            row = rows.get(planned_id)
            if row is None:
                row = RadarPlannedRow(
                    planned_id=planned.id,
                    name=planned.name,
                    amount=planned.amount,
                    frequency=planned.frequency,
                    interval=planned.interval,
                    start_date=planned.start_date,
                    linked_count=0,
                    linked_dates=[],
                )
                rows[planned_id] = row
            row.linked_count += 1
            row.linked_dates.append(tx_date)
        return sorted(rows.values(), key=lambda r: r.name)

    async def linked_history(self, planned_id: int) -> builtins.list[datetime.date]:
        """Dates of the historical charges linked to one plan."""
        planned = await self.session.get(PlannedTransaction, planned_id)
        if planned is None:
            raise NotFoundError(f"Planned transaction {planned_id} not found")
        result = await self.session.execute(
            select(Transaction.date)
            .where(
                Transaction.planned_transaction_id == planned_id,
                Transaction.date < planned.start_date,
            )
            .order_by(Transaction.date)
        )
        return list(result.scalars().all())

    # ── Exclusion sources ─────────────────────────────────────────────────

    async def _subscription_category_ids(self) -> set[int]:
        """Subscriptions root + its direct children — handled by the sub tracker.

        One level deep, matching ``SubscriptionService`` and the tree the
        category service actually builds. If the Subscriptions tree ever grows
        a third level, both walks need to recurse together.
        """
        root_result = await self.session.execute(
            select(Category.id).where(Category.is_subscriptions_root.is_(True))
        )
        root_id = root_result.scalar_one_or_none()
        if root_id is None:
            return set()
        ids = {root_id}
        children = await self.session.execute(
            select(Category.id).where(Category.parent_id == root_id)
        )
        ids.update(children.scalars().all())
        return ids

    async def _tracked_sources(self) -> tuple[set[int], set[str]]:
        """Payees / merchant keys already covered by a plan or a subscription."""
        payee_ids: set[int] = set()
        keys: set[str] = set()

        subs = await self.session.execute(
            select(Subscription.payee_id, Subscription.name).where(
                Subscription.status != SubscriptionStatus.CANCELLED
            )
        )
        for payee_id, name in subs.all():
            if payee_id is not None:
                payee_ids.add(payee_id)
            if name:
                keys.add(merchant_key_from_description(name))

        planned = await self.session.execute(
            select(PlannedTransaction.name).where(PlannedTransaction.is_active.is_(True))
        )
        keys.update(merchant_key_from_description(name) for name in planned.scalars().all() if name)

        keys.discard("")
        return payee_ids, keys

    async def _dismissed_sources(self) -> tuple[set[int], set[str]]:
        result = await self.session.execute(
            select(DismissedCandidate.payee_id, DismissedCandidate.merchant_key).where(
                DismissedCandidate.kind == DismissedCandidateKind.UNPLANNED
            )
        )
        payee_ids: set[int] = set()
        keys: set[str] = set()
        for payee_id, merchant_key in result.all():
            if payee_id is not None:
                payee_ids.add(payee_id)
            elif merchant_key:
                keys.add(merchant_key)
        return payee_ids, keys


# ── Helpers ──────────────────────────────────────────────────────────────────


def _amount_bucket(amount: Decimal) -> str:
    """Coarse bucket used as part of the dismissal key."""
    return str(int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)))


def _median(values: builtins.list[Decimal]) -> Decimal:
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        return ordered[mid]
    return ((ordered[mid - 1] + ordered[mid]) / 2).quantize(_CENTS, rounding=ROUND_HALF_UP)


def _cadence(average_gap_days: int) -> tuple[RecurrenceFrequency, int]:
    """Map an average gap onto the closest recurrence the planner can express."""
    if average_gap_days >= YEARLY_GAP_FLOOR_DAYS:
        years = max(1, round(average_gap_days / 365))
        return RecurrenceFrequency.YEARLY, years
    months = max(2, round(average_gap_days / 30))
    return RecurrenceFrequency.MONTHLY, months


def _candidate_from_occurrences(
    occurrences: builtins.list[_Occurrence], *, name: str, payee_id: int | None
) -> RadarCandidate | None:
    """Return a candidate when the charges form a slow, drifting rhythm."""
    if len(occurrences) < MIN_OCCURRENCES:
        return None
    ordered = sorted(occurrences, key=lambda o: o.date)

    gaps = [(ordered[i].date - ordered[i - 1].date).days for i in range(1, len(ordered))]
    if any(gap < MIN_GAP_DAYS or gap > MAX_GAP_DAYS for gap in gaps):
        return None

    typical = _median([o.amount for o in ordered])
    if typical <= 0:
        return None
    lower = typical * (Decimal("1") - AMOUNT_TOLERANCE_PCT)
    upper = typical * (Decimal("1") + AMOUNT_TOLERANCE_PCT)
    if any(o.amount < lower or o.amount > upper for o in ordered):
        return None

    average_gap = round(sum(gaps) / len(gaps))
    frequency, interval = _cadence(average_gap)
    last = ordered[-1]
    yearly = (typical * DAYS_PER_YEAR / Decimal(average_gap)).quantize(
        _CENTS, rounding=ROUND_HALF_UP
    )

    return RadarCandidate(
        payee_id=payee_id,
        source_name=name,
        typical_amount=typical.quantize(_CENTS, rounding=ROUND_HALF_UP),
        occurrences=len(ordered),
        first_seen_at=ordered[0].date,
        last_seen_at=last.date,
        average_gap_days=average_gap,
        next_expected_at=last.date + datetime.timedelta(days=average_gap),
        frequency=frequency,
        interval=interval,
        yearly_estimate=yearly,
        account_id=last.account_id,
        category_id=_dominant_category_id(ordered),
        occurrence_dates=[o.date for o in ordered],
        transaction_ids=[o.transaction_id for o in ordered],
    )


def _dominant_category_id(occurrences: builtins.list[_Occurrence]) -> int | None:
    """The category most of the charges were filed under, if any."""
    counts = Counter(o.category_id for o in occurrences if o.category_id is not None)
    if not counts:
        return None
    return counts.most_common(1)[0][0]


__all__ = ["UnplannedRadarService", "summarise"]
