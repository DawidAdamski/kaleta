"""Unit tests for SubscriptionService — uses in-memory SQLite."""

from __future__ import annotations

import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.account import AccountType
from kaleta.models.category import CategoryType
from kaleta.models.payee import Payee
from kaleta.models.subscription import SubscriptionStatus
from kaleta.models.transaction import Transaction, TransactionType
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.category import CategoryCreate
from kaleta.schemas.subscription import SubscriptionCreate, SubscriptionUpdate
from kaleta.services import (
    AccountService,
    CategoryService,
    SubscriptionService,
)


async def _seed_setup(session: AsyncSession) -> tuple[int, int]:
    """Create an account + an expense category. Returns (account_id, cat_id)."""
    acc = await AccountService(session).create(
        AccountCreate(name="Checking", type=AccountType.CHECKING, balance=Decimal("0"))
    )
    cat = await CategoryService(session).create(
        CategoryCreate(name="Streaming", type=CategoryType.EXPENSE)
    )
    return acc.id, cat.id


async def _add_payee(session: AsyncSession, name: str) -> Payee:
    payee = Payee(name=name)
    session.add(payee)
    await session.commit()
    await session.refresh(payee)
    return payee


async def _add_expense(
    session: AsyncSession,
    *,
    account_id: int,
    category_id: int,
    payee_id: int,
    amount: Decimal,
    date: datetime.date,
) -> None:
    tx = Transaction(
        account_id=account_id,
        category_id=category_id,
        payee_id=payee_id,
        type=TransactionType.EXPENSE,
        amount=amount,
        date=date,
        description=f"exp-{date}",
        is_internal_transfer=False,
    )
    session.add(tx)
    await session.commit()


# ── CRUD ──────────────────────────────────────────────────────────────────────


class TestCrud:
    async def test_create_persists(self, session: AsyncSession):
        svc = SubscriptionService(session)
        sub = await svc.create(
            SubscriptionCreate(
                name="Netflix",
                amount=Decimal("49.99"),
                cadence_days=30,
                first_seen_at=datetime.date(2025, 1, 1),
            )
        )
        assert sub.id is not None
        assert sub.name == "Netflix"
        assert sub.status == SubscriptionStatus.ACTIVE
        # next_expected_at auto-projected from first_seen_at
        assert sub.next_expected_at is not None

    async def test_list_filters_by_status(self, session: AsyncSession):
        svc = SubscriptionService(session)
        a = await svc.create(
            SubscriptionCreate(
                name="Spotify", amount=Decimal("19.99"), cadence_days=30
            )
        )
        b = await svc.create(
            SubscriptionCreate(name="iCloud", amount=Decimal("4.99"), cadence_days=30)
        )
        await svc.cancel(b.id)
        active = await svc.list(status=SubscriptionStatus.ACTIVE)
        assert len(active) == 1
        assert active[0].id == a.id
        cancelled = await svc.list(status=SubscriptionStatus.CANCELLED)
        assert len(cancelled) == 1
        assert cancelled[0].id == b.id

    async def test_update_patches_fields(self, session: AsyncSession):
        svc = SubscriptionService(session)
        sub = await svc.create(
            SubscriptionCreate(name="X", amount=Decimal("10"), cadence_days=30)
        )
        updated = await svc.update(sub.id, SubscriptionUpdate(amount=Decimal("12.50")))
        assert updated is not None
        assert updated.amount == Decimal("12.50")
        assert updated.name == "X"  # unchanged

    async def test_update_missing_returns_none(self, session: AsyncSession):
        svc = SubscriptionService(session)
        assert await svc.update(999, SubscriptionUpdate(name="N")) is None

    async def test_delete_removes(self, session: AsyncSession):
        svc = SubscriptionService(session)
        sub = await svc.create(
            SubscriptionCreate(name="X", amount=Decimal("10"), cadence_days=30)
        )
        assert await svc.delete(sub.id) is True
        assert await svc.get(sub.id) is None

    async def test_delete_missing_returns_false(self, session: AsyncSession):
        assert await SubscriptionService(session).delete(999) is False


# ── Status transitions ───────────────────────────────────────────────────────


class TestTransitions:
    async def test_mute_sets_until_one_cycle_away(self, session: AsyncSession):
        svc = SubscriptionService(session)
        sub = await svc.create(
            SubscriptionCreate(name="Netflix", amount=Decimal("50"), cadence_days=30)
        )
        today = datetime.date(2026, 4, 1)
        muted = await svc.mute_one_cycle(sub.id, today=today)
        assert muted is not None
        assert muted.status == SubscriptionStatus.MUTED
        assert muted.muted_until == today + datetime.timedelta(days=30)

    async def test_cancel_stamps_date_and_clears_next(self, session: AsyncSession):
        svc = SubscriptionService(session)
        sub = await svc.create(
            SubscriptionCreate(
                name="X",
                amount=Decimal("10"),
                cadence_days=30,
                first_seen_at=datetime.date(2025, 1, 1),
            )
        )
        today = datetime.date(2026, 4, 1)
        cancelled = await svc.cancel(sub.id, today=today)
        assert cancelled is not None
        assert cancelled.status == SubscriptionStatus.CANCELLED
        assert cancelled.cancelled_at == today
        assert cancelled.next_expected_at is None

    async def test_reactivate_clears_mute_and_cancel(self, session: AsyncSession):
        svc = SubscriptionService(session)
        sub = await svc.create(
            SubscriptionCreate(
                name="X",
                amount=Decimal("10"),
                cadence_days=30,
                first_seen_at=datetime.date(2025, 1, 1),
            )
        )
        await svc.cancel(sub.id, today=datetime.date(2026, 4, 1))
        restored = await svc.reactivate(sub.id)
        assert restored is not None
        assert restored.status == SubscriptionStatus.ACTIVE
        assert restored.cancelled_at is None
        assert restored.muted_until is None


# ── Totals ───────────────────────────────────────────────────────────────────


class TestTotals:
    async def test_totals_sum_only_active(self, session: AsyncSession):
        svc = SubscriptionService(session)
        await svc.create(
            SubscriptionCreate(name="A", amount=Decimal("30"), cadence_days=30)
        )
        await svc.create(
            SubscriptionCreate(name="B", amount=Decimal("60"), cadence_days=30)
        )
        cancelled = await svc.create(
            SubscriptionCreate(name="C", amount=Decimal("50"), cadence_days=30)
        )
        await svc.cancel(cancelled.id)

        t = await svc.totals()
        assert t.active_count == 2
        # Both monthly: 30 + 60 = 90/mo, 1080/yr.
        assert t.monthly_total == Decimal("90.00")
        assert t.yearly_total == Decimal("1080.00")

    async def test_yearly_sub_normalises_to_thirty_over_cadence(
        self, session: AsyncSession
    ):
        svc = SubscriptionService(session)
        await svc.create(
            SubscriptionCreate(name="Y", amount=Decimal("365"), cadence_days=365)
        )
        t = await svc.totals()
        # 365 × 30 / 365 = 30/mo
        assert t.monthly_total == Decimal("30.00")


# ── Detector ─────────────────────────────────────────────────────────────────


class TestDetector:
    async def test_detects_monthly_pattern(self, session: AsyncSession):
        acc, cat = await _seed_setup(session)
        payee = await _add_payee(session, "Netflix")
        today = datetime.date(2026, 4, 1)
        for months_back in (0, 1, 2, 3):
            tx_date = today - datetime.timedelta(days=30 * months_back)
            await _add_expense(
                session,
                account_id=acc,
                category_id=cat,
                payee_id=payee.id,
                amount=Decimal("49.99"),
                date=tx_date,
            )
        svc = SubscriptionService(session)
        candidates = await svc.detect_candidates(today=today)
        assert len(candidates) == 1
        c = candidates[0]
        assert c.payee_name == "Netflix"
        assert c.cadence_days == 30
        assert c.occurrences == 4

    async def test_detects_yearly_pattern(self, session: AsyncSession):
        acc, cat = await _seed_setup(session)
        payee = await _add_payee(session, "Domain")
        today = datetime.date(2026, 4, 1)
        # 365 days apart
        await _add_expense(
            session,
            account_id=acc,
            category_id=cat,
            payee_id=payee.id,
            amount=Decimal("60"),
            date=today - datetime.timedelta(days=365),
        )
        await _add_expense(
            session,
            account_id=acc,
            category_id=cat,
            payee_id=payee.id,
            amount=Decimal("60"),
            date=today - datetime.timedelta(days=1),
        )
        svc = SubscriptionService(session)
        candidates = await svc.detect_candidates(today=today)
        assert len(candidates) == 1
        assert candidates[0].cadence_days == 365

    async def test_excludes_already_tracked_payees(self, session: AsyncSession):
        acc, cat = await _seed_setup(session)
        payee = await _add_payee(session, "Spotify")
        today = datetime.date(2026, 4, 1)
        for months_back in (0, 1, 2):
            tx_date = today - datetime.timedelta(days=30 * months_back)
            await _add_expense(
                session,
                account_id=acc,
                category_id=cat,
                payee_id=payee.id,
                amount=Decimal("19.99"),
                date=tx_date,
            )
        svc = SubscriptionService(session)
        # Pre-create a subscription for the same payee
        await svc.create(
            SubscriptionCreate(
                name="Spotify",
                amount=Decimal("19.99"),
                cadence_days=30,
                payee_id=payee.id,
            )
        )
        candidates = await svc.detect_candidates(today=today)
        assert candidates == []

    async def test_ignores_single_charges(self, session: AsyncSession):
        acc, cat = await _seed_setup(session)
        payee = await _add_payee(session, "OneOff")
        await _add_expense(
            session,
            account_id=acc,
            category_id=cat,
            payee_id=payee.id,
            amount=Decimal("100"),
            date=datetime.date(2026, 4, 1),
        )
        svc = SubscriptionService(session)
        candidates = await svc.detect_candidates(today=datetime.date(2026, 4, 1))
        assert candidates == []

    async def test_create_from_candidate_tracks_it(self, session: AsyncSession):
        acc, cat = await _seed_setup(session)
        payee = await _add_payee(session, "Netflix")
        today = datetime.date(2026, 4, 1)
        for months_back in (0, 1, 2):
            await _add_expense(
                session,
                account_id=acc,
                category_id=cat,
                payee_id=payee.id,
                amount=Decimal("49.99"),
                date=today - datetime.timedelta(days=30 * months_back),
            )
        svc = SubscriptionService(session)
        candidates = await svc.detect_candidates(today=today)
        assert len(candidates) == 1
        sub = await svc.create_from_candidate(candidates[0])
        assert sub.payee_id == payee.id
        assert sub.name == "Netflix"

        # A second detector run should now exclude it
        candidates2 = await svc.detect_candidates(today=today)
        assert candidates2 == []


# ── Renewals ─────────────────────────────────────────────────────────────────


class TestRenewals:
    async def test_upcoming_within_30_days(self, session: AsyncSession):
        svc = SubscriptionService(session)
        today = datetime.date(2026, 4, 1)
        a = await svc.create(
            SubscriptionCreate(
                name="Soon", amount=Decimal("10"), cadence_days=30
            )
        )
        b = await svc.create(
            SubscriptionCreate(
                name="Far", amount=Decimal("10"), cadence_days=30
            )
        )
        await svc.update(
            a.id, SubscriptionUpdate(next_expected_at=today + datetime.timedelta(days=7))
        )
        await svc.update(
            b.id, SubscriptionUpdate(next_expected_at=today + datetime.timedelta(days=45))
        )
        upcoming = await svc.upcoming_renewals(today=today)
        assert len(upcoming) == 1
        assert upcoming[0].name == "Soon"
        assert upcoming[0].days_away == 7

    async def test_muted_and_cancelled_excluded(self, session: AsyncSession):
        svc = SubscriptionService(session)
        today = datetime.date(2026, 4, 1)
        sub = await svc.create(
            SubscriptionCreate(
                name="X",
                amount=Decimal("10"),
                cadence_days=30,
                next_expected_at=today + datetime.timedelta(days=5),
            )
        )
        await svc.cancel(sub.id, today=today)
        upcoming = await svc.upcoming_renewals(today=today)
        assert upcoming == []
