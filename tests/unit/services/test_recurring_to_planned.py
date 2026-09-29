# SPDX-License-Identifier: AGPL-3.0-or-later
"""Recurring detection → planned transaction, and plan price drift.

Covers the service layer of ``KAL-REC-002`` (create a planned transaction
from a detected recurring charge) and ``KAL-REC-004`` (a new payment at a
different price is flagged against its plan).
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import NotFoundError, ValidationError
from kaleta.models.account import AccountType
from kaleta.models.category import CategoryType
from kaleta.models.payee import Payee
from kaleta.models.planned_transaction import PlannedTransaction, RecurrenceFrequency
from kaleta.models.transaction import Transaction, TransactionType
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.category import CategoryCreate
from kaleta.schemas.planned_transaction import PlannedTransactionCreate
from kaleta.services import (
    AccountService,
    CategoryService,
    DedupeService,
    PlannedPriceDriftService,
    PlannedTransactionService,
    SubscriptionService,
)

TODAY = datetime.date.today()


async def _setup(session: AsyncSession) -> tuple[int, int]:
    acc = await AccountService(session).create(
        AccountCreate(name="Checking", type=AccountType.CHECKING, balance=Decimal("0"))
    )
    cat = await CategoryService(session).create(
        CategoryCreate(name="Streaming", type=CategoryType.EXPENSE)
    )
    return acc.id, cat.id


async def _payee(session: AsyncSession, name: str) -> int:
    payee = Payee(name=name)
    session.add(payee)
    await session.commit()
    return payee.id


async def _expense(
    session: AsyncSession,
    *,
    account_id: int,
    category_id: int | None,
    payee_id: int | None,
    amount: str,
    date: datetime.date,
    description: str = "charge",
    planned_transaction_id: int | None = None,
) -> int:
    tx = Transaction(
        account_id=account_id,
        category_id=category_id,
        payee_id=payee_id,
        type=TransactionType.EXPENSE,
        amount=Decimal(amount),
        date=date,
        description=description,
        is_internal_transfer=False,
        planned_transaction_id=planned_transaction_id,
    )
    session.add(tx)
    await session.commit()
    return tx.id


async def _three_monthly(
    session: AsyncSession, account_id: int, category_id: int, payee_id: int | None
) -> list[int]:
    """Three consecutive months of 49.99 — the KAL-REC-001/002 fixture."""
    return [
        await _expense(
            session,
            account_id=account_id,
            category_id=category_id,
            payee_id=payee_id,
            amount="49.99",
            date=TODAY - datetime.timedelta(days=30 * i),
            description="NETFLIX.COM /Amsterdam",
        )
        for i in range(3)
    ]


async def _plan(
    session: AsyncSession,
    account_id: int,
    *,
    name: str = "Netflix",
    amount: str = "49.99",
    payee_id: int | None = None,
) -> PlannedTransaction:
    return await PlannedTransactionService(session).create(
        PlannedTransactionCreate(
            name=name,
            amount=Decimal(amount),
            type=TransactionType.EXPENSE,
            account_id=account_id,
            payee_id=payee_id,
            frequency=RecurrenceFrequency.MONTHLY,
            start_date=TODAY + datetime.timedelta(days=5),
        )
    )


# ── KAL-REC-002 ───────────────────────────────────────────────────────────────


class TestCreatePlannedFromDetection:
    async def test_detection_becomes_monthly_plan_and_is_handled(
        self, session: AsyncSession
    ) -> None:
        """Covers: KAL-REC-002

        A detected "Netflix 49.99 monthly" turns into a monthly planned
        transaction for 49.99 to "Netflix", and the detection is handled.
        """
        acc_id, cat_id = await _setup(session)
        netflix = await _payee(session, "Netflix")
        await _three_monthly(session, acc_id, cat_id, netflix)
        svc = SubscriptionService(session)
        [cand] = await svc.detect_candidates()

        planned = await svc.create_planned_from_candidate(cand)

        assert planned.name == "Netflix"
        assert planned.amount == Decimal("49.99")
        assert planned.frequency == RecurrenceFrequency.MONTHLY
        assert planned.interval == 1
        assert planned.type == TransactionType.EXPENSE
        assert planned.payee_id == netflix
        assert planned.account_id == acc_id
        assert planned.category_id == cat_id
        assert planned.start_date > TODAY
        assert await svc.detect_candidates() == []

    async def test_history_is_linked_to_the_new_plan(self, session: AsyncSession) -> None:
        """Covers: KAL-REC-002 — same creation path as the radar (KAL-REC-003)."""
        acc_id, cat_id = await _setup(session)
        netflix = await _payee(session, "Netflix")
        tx_ids = await _three_monthly(session, acc_id, cat_id, netflix)
        svc = SubscriptionService(session)
        [cand] = await svc.detect_candidates()
        assert sorted(cand.transaction_ids) == sorted(tx_ids)

        planned = await svc.create_planned_from_candidate(cand)

        linked = await session.execute(
            select(Transaction.id).where(Transaction.planned_transaction_id == planned.id)
        )
        assert sorted(linked.scalars().all()) == sorted(tx_ids)

    async def test_payee_less_detection_is_retired_by_plan_name(
        self, session: AsyncSession
    ) -> None:
        """Covers: KAL-REC-002 — a description-only detection is handled too."""
        acc_id, cat_id = await _setup(session)
        await _three_monthly(session, acc_id, cat_id, None)
        svc = SubscriptionService(session)
        [cand] = await svc.detect_candidates()
        assert cand.payee_name == "NETFLIX.COM"

        planned = await svc.create_planned_from_candidate(cand)

        assert planned.payee_id is None
        assert planned.name == "NETFLIX.COM"
        assert await svc.detect_candidates() == []

    async def test_inactive_plan_does_not_retire_detection(self, session: AsyncSession) -> None:
        acc_id, cat_id = await _setup(session)
        netflix = await _payee(session, "Netflix")
        await _three_monthly(session, acc_id, cat_id, netflix)
        planned = await _plan(session, acc_id, payee_id=netflix)
        await PlannedTransactionService(session).toggle_active(planned.id)

        assert len(await SubscriptionService(session).detect_candidates()) == 1

    async def test_candidate_without_account_is_rejected(self, session: AsyncSession) -> None:
        acc_id, cat_id = await _setup(session)
        netflix = await _payee(session, "Netflix")
        await _three_monthly(session, acc_id, cat_id, netflix)
        svc = SubscriptionService(session)
        [cand] = await svc.detect_candidates()

        with pytest.raises(ValidationError):
            await svc.create_planned_from_candidate(cand.model_copy(update={"account_id": None}))

    async def test_yearly_detection_becomes_yearly_plan(self, session: AsyncSession) -> None:
        acc_id, cat_id = await _setup(session)
        domain = await _payee(session, "Domain")
        for days_ago in (0, 365):
            await _expense(
                session,
                account_id=acc_id,
                category_id=cat_id,
                payee_id=domain,
                amount="120.00",
                date=TODAY - datetime.timedelta(days=days_ago),
            )
        svc = SubscriptionService(session)
        [cand] = await svc.detect_candidates()

        planned = await svc.create_planned_from_candidate(cand)

        assert planned.frequency == RecurrenceFrequency.YEARLY
        assert planned.amount == Decimal("120.00")


# ── KAL-REC-004 ───────────────────────────────────────────────────────────────


class TestPriceDrift:
    async def test_new_payment_at_new_price_is_flagged(self, session: AsyncSession) -> None:
        """Covers: KAL-REC-004

        Given a planned transaction "Netflix 49.99 monthly", a new matching
        payment at 54.99 is flagged as a price change.
        """
        acc_id, cat_id = await _setup(session)
        netflix = await _payee(session, "Netflix")
        planned = await _plan(session, acc_id, payee_id=netflix)
        await _expense(
            session,
            account_id=acc_id,
            category_id=cat_id,
            payee_id=netflix,
            amount="54.99",
            date=TODAY,
        )

        [drift] = await PlannedPriceDriftService(session).detect()

        assert drift.planned_id == planned.id
        assert drift.name == "Netflix"
        assert drift.planned_amount == Decimal("49.99")
        assert drift.payment_amount == Decimal("54.99")
        assert drift.payment_date == TODAY
        assert drift.change_pct == Decimal("10.0")

    async def test_accepting_updates_the_plan_and_clears_the_flag(
        self, session: AsyncSession
    ) -> None:
        """Covers: KAL-REC-004 — "offers to update the plan"."""
        acc_id, cat_id = await _setup(session)
        netflix = await _payee(session, "Netflix")
        planned = await _plan(session, acc_id, payee_id=netflix)
        await _expense(
            session,
            account_id=acc_id,
            category_id=cat_id,
            payee_id=netflix,
            amount="54.99",
            date=TODAY,
        )
        svc = PlannedPriceDriftService(session)

        updated = await svc.accept(planned.id, Decimal("54.99"))

        assert updated.amount == Decimal("54.99")
        assert await svc.detect() == []

    async def test_change_within_tolerance_is_not_flagged(self, session: AsyncSession) -> None:
        acc_id, cat_id = await _setup(session)
        netflix = await _payee(session, "Netflix")
        await _plan(session, acc_id, payee_id=netflix)
        await _expense(
            session,
            account_id=acc_id,
            category_id=cat_id,
            payee_id=netflix,
            amount="52.48",  # +4.98 % — inside the 5 % tolerance
            date=TODAY,
        )

        assert await PlannedPriceDriftService(session).detect() == []

    async def test_price_drop_is_flagged_with_negative_change(self, session: AsyncSession) -> None:
        acc_id, cat_id = await _setup(session)
        netflix = await _payee(session, "Netflix")
        await _plan(session, acc_id, payee_id=netflix)
        await _expense(
            session,
            account_id=acc_id,
            category_id=cat_id,
            payee_id=netflix,
            amount="39.99",
            date=TODAY,
        )

        [drift] = await PlannedPriceDriftService(session).detect()

        assert drift.change_pct == Decimal("-20.0")

    async def test_payment_before_the_plan_existed_is_not_new(self, session: AsyncSession) -> None:
        acc_id, cat_id = await _setup(session)
        netflix = await _payee(session, "Netflix")
        await _expense(
            session,
            account_id=acc_id,
            category_id=cat_id,
            payee_id=netflix,
            amount="54.99",
            date=TODAY - datetime.timedelta(days=2),
        )
        await _plan(session, acc_id, payee_id=netflix)

        assert await PlannedPriceDriftService(session).detect() == []

    async def test_posted_occurrence_is_not_a_new_payment(self, session: AsyncSession) -> None:
        acc_id, cat_id = await _setup(session)
        netflix = await _payee(session, "Netflix")
        planned = await _plan(session, acc_id, payee_id=netflix)
        other = await _plan(session, acc_id, name="Other", amount="54.99")
        await _expense(
            session,
            account_id=acc_id,
            category_id=cat_id,
            payee_id=netflix,
            amount="54.99",
            date=TODAY,
            planned_transaction_id=other.id,
        )

        drifts = await PlannedPriceDriftService(session).detect()

        assert planned.id not in {d.planned_id for d in drifts}

    async def test_latest_payment_decides(self, session: AsyncSession) -> None:
        acc_id, cat_id = await _setup(session)
        netflix = await _payee(session, "Netflix")
        await _plan(session, acc_id, payee_id=netflix)
        for days_ahead, amount in ((0, "54.99"), (1, "49.99")):
            await _expense(
                session,
                account_id=acc_id,
                category_id=cat_id,
                payee_id=netflix,
                amount=amount,
                date=TODAY + datetime.timedelta(days=days_ahead),
            )

        assert await PlannedPriceDriftService(session).detect() == []

    async def test_payee_less_plan_matches_by_description(self, session: AsyncSession) -> None:
        acc_id, cat_id = await _setup(session)
        await _plan(session, acc_id, name="NETFLIX.COM")
        await _expense(
            session,
            account_id=acc_id,
            category_id=cat_id,
            payee_id=None,
            amount="54.99",
            date=TODAY,
            description="NETFLIX.COM /Amsterdam",
        )

        [drift] = await PlannedPriceDriftService(session).detect()

        assert drift.name == "NETFLIX.COM"

    async def test_other_payee_does_not_match(self, session: AsyncSession) -> None:
        acc_id, cat_id = await _setup(session)
        netflix = await _payee(session, "Netflix")
        spotify = await _payee(session, "Spotify")
        await _plan(session, acc_id, payee_id=netflix)
        await _expense(
            session,
            account_id=acc_id,
            category_id=cat_id,
            payee_id=spotify,
            amount="23.99",
            date=TODAY,
        )

        assert await PlannedPriceDriftService(session).detect() == []

    async def test_accept_unknown_plan_raises(self, session: AsyncSession) -> None:
        with pytest.raises(NotFoundError):
            await PlannedPriceDriftService(session).accept(999, Decimal("54.99"))

    async def test_accept_non_positive_amount_raises(self, session: AsyncSession) -> None:
        acc_id, _cat_id = await _setup(session)
        planned = await _plan(session, acc_id)
        with pytest.raises(ValidationError):
            await PlannedPriceDriftService(session).accept(planned.id, Decimal("0"))

    async def test_payee_merge_keeps_the_plan_matched(self, session: AsyncSession) -> None:
        acc_id, _cat_id = await _setup(session)
        keeper = await _payee(session, "Netflix")
        victim = await _payee(session, "NETFLIX INTERNATIONAL")
        planned = await _plan(session, acc_id, payee_id=victim)

        await DedupeService(session).merge_payees(keeper_id=keeper, other_ids=[victim])

        await session.refresh(planned)
        assert planned.payee_id == keeper
