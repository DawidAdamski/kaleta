# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for UnplannedRadarService — uses in-memory SQLite."""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.account import AccountType
from kaleta.models.category import CategoryType
from kaleta.models.payee import Payee
from kaleta.models.planned_transaction import RecurrenceFrequency
from kaleta.models.transaction import Transaction, TransactionType
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.category import CategoryCreate
from kaleta.schemas.planned_transaction import PlannedTransactionCreate
from kaleta.schemas.subscription import SubscriptionCreate
from kaleta.services import (
    AccountService,
    CategoryService,
    PlannedTransactionService,
    SubscriptionService,
    UnplannedRadarService,
)
from kaleta.services.unplanned_radar_service import summarise

TODAY = datetime.date(2026, 9, 4)


async def _seed_setup(session: AsyncSession) -> tuple[int, int]:
    """Create an account + an expense category. Returns (account_id, cat_id)."""
    acc = await AccountService(session).create(
        AccountCreate(name="Checking", type=AccountType.CHECKING, balance=Decimal("0"))
    )
    cat = await CategoryService(session).create(
        CategoryCreate(name="Car", type=CategoryType.EXPENSE)
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
    category_id: int | None,
    payee_id: int | None,
    amount: Decimal,
    date: datetime.date,
    description: str | None = None,
    is_internal_transfer: bool = False,
) -> Transaction:
    tx = Transaction(
        account_id=account_id,
        category_id=category_id,
        payee_id=payee_id,
        type=TransactionType.EXPENSE,
        amount=amount,
        date=date,
        description=description or f"exp-{date}",
        is_internal_transfer=is_internal_transfer,
    )
    session.add(tx)
    await session.commit()
    await session.refresh(tx)
    return tx


async def _seed_yearly_car_service(
    session: AsyncSession, *, payee_name: str = "Serwis Auto"
) -> tuple[int, int, int]:
    """Two car-service charges a year apart, drifting in price."""
    account_id, category_id = await _seed_setup(session)
    payee = await _add_payee(session, payee_name)
    await _add_expense(
        session,
        account_id=account_id,
        category_id=category_id,
        payee_id=payee.id,
        amount=Decimal("1200.00"),
        date=datetime.date(2024, 9, 10),
    )
    await _add_expense(
        session,
        account_id=account_id,
        category_id=category_id,
        payee_id=payee.id,
        amount=Decimal("1400.00"),
        date=datetime.date(2025, 9, 10),
    )
    return account_id, category_id, payee.id


# ── Detection ────────────────────────────────────────────────────────────────


class TestDetect:
    async def test_yearly_repeat_is_a_candidate(self, session: AsyncSession):
        await _seed_yearly_car_service(session)

        [candidate] = await UnplannedRadarService(session).detect(today=TODAY)

        assert candidate.source_name == "Serwis Auto"
        assert candidate.occurrences == 2
        assert candidate.typical_amount == Decimal("1300.00")
        assert candidate.first_seen_at == datetime.date(2024, 9, 10)
        assert candidate.last_seen_at == datetime.date(2025, 9, 10)
        assert candidate.average_gap_days == 365
        assert candidate.next_expected_at == datetime.date(2026, 9, 10)
        assert candidate.frequency == RecurrenceFrequency.YEARLY
        assert candidate.interval == 1
        assert candidate.yearly_estimate == Decimal("1300.00")

    async def test_single_occurrence_is_not_a_pattern(self, session: AsyncSession):
        account_id, category_id = await _seed_setup(session)
        payee = await _add_payee(session, "Dentysta")
        await _add_expense(
            session,
            account_id=account_id,
            category_id=category_id,
            payee_id=payee.id,
            amount=Decimal("500.00"),
            date=datetime.date(2025, 3, 1),
        )

        assert await UnplannedRadarService(session).detect(today=TODAY) == []

    async def test_monthly_rhythm_is_left_to_the_subscription_detector(self, session: AsyncSession):
        account_id, category_id = await _seed_setup(session)
        payee = await _add_payee(session, "Netflix")
        for month in (5, 6, 7):
            await _add_expense(
                session,
                account_id=account_id,
                category_id=category_id,
                payee_id=payee.id,
                amount=Decimal("49.99"),
                date=datetime.date(2026, month, 10),
            )

        assert await UnplannedRadarService(session).detect(today=TODAY) == []

    async def test_quarterly_repeat_maps_to_a_monthly_interval(self, session: AsyncSession):
        account_id, category_id = await _seed_setup(session)
        payee = await _add_payee(session, "Ubezpieczenie")
        for date in (
            datetime.date(2026, 1, 15),
            datetime.date(2026, 4, 15),
            datetime.date(2026, 7, 15),
        ):
            await _add_expense(
                session,
                account_id=account_id,
                category_id=category_id,
                payee_id=payee.id,
                amount=Decimal("300.00"),
                date=date,
            )

        [candidate] = await UnplannedRadarService(session).detect(today=TODAY)

        assert candidate.frequency == RecurrenceFrequency.MONTHLY
        assert candidate.interval == 3
        assert candidate.occurrences == 3

    async def test_amount_drift_beyond_tolerance_is_rejected(self, session: AsyncSession):
        account_id, category_id = await _seed_setup(session)
        payee = await _add_payee(session, "Losowy sklep")
        await _add_expense(
            session,
            account_id=account_id,
            category_id=category_id,
            payee_id=payee.id,
            amount=Decimal("100.00"),
            date=datetime.date(2025, 2, 1),
        )
        await _add_expense(
            session,
            account_id=account_id,
            category_id=category_id,
            payee_id=payee.id,
            amount=Decimal("900.00"),
            date=datetime.date(2026, 2, 1),
        )

        assert await UnplannedRadarService(session).detect(today=TODAY) == []

    async def test_gap_beyond_the_ceiling_is_a_coincidence(self, session: AsyncSession):
        account_id, category_id = await _seed_setup(session)
        payee = await _add_payee(session, "Weterynarz")
        await _add_expense(
            session,
            account_id=account_id,
            category_id=category_id,
            payee_id=payee.id,
            amount=Decimal("400.00"),
            date=datetime.date(2024, 1, 5),
        )
        await _add_expense(
            session,
            account_id=account_id,
            category_id=category_id,
            payee_id=payee.id,
            amount=Decimal("400.00"),
            date=datetime.date(2026, 1, 5),
        )

        assert await UnplannedRadarService(session).detect(today=TODAY) == []

    async def test_payee_less_rows_group_by_description(self, session: AsyncSession):
        account_id, category_id = await _seed_setup(session)
        for date in (datetime.date(2025, 4, 2), datetime.date(2026, 4, 2)):
            await _add_expense(
                session,
                account_id=account_id,
                category_id=category_id,
                payee_id=None,
                amount=Decimal("820.00"),
                date=date,
                description="PRZEGLAD TECHNICZNY /Warszawa",
            )

        [candidate] = await UnplannedRadarService(session).detect(today=TODAY)

        assert candidate.payee_id is None
        assert candidate.source_name == "PRZEGLAD TECHNICZNY"

    async def test_internal_transfers_are_ignored(self, session: AsyncSession):
        account_id, category_id = await _seed_setup(session)
        payee = await _add_payee(session, "Wlasne konto")
        for date in (datetime.date(2025, 6, 1), datetime.date(2026, 6, 1)):
            await _add_expense(
                session,
                account_id=account_id,
                category_id=category_id,
                payee_id=payee.id,
                amount=Decimal("2000.00"),
                date=date,
                is_internal_transfer=True,
            )

        assert await UnplannedRadarService(session).detect(today=TODAY) == []

    async def test_active_subscription_covers_its_payee(self, session: AsyncSession):
        _, _, payee_id = await _seed_yearly_car_service(session)
        await SubscriptionService(session).create(
            SubscriptionCreate(
                name="Serwis Auto",
                amount=Decimal("1300.00"),
                cadence_days=365,
                payee_id=payee_id,
            )
        )

        assert await UnplannedRadarService(session).detect(today=TODAY) == []

    async def test_existing_planned_transaction_covers_the_source(self, session: AsyncSession):
        account_id, _, _ = await _seed_yearly_car_service(session)
        await PlannedTransactionService(session).create(
            PlannedTransactionCreate(
                name="Serwis Auto",
                amount=Decimal("1300.00"),
                type=TransactionType.EXPENSE,
                account_id=account_id,
                frequency=RecurrenceFrequency.YEARLY,
                start_date=datetime.date(2026, 9, 10),
            )
        )

        assert await UnplannedRadarService(session).detect(today=TODAY) == []

    async def test_charges_under_the_subscriptions_tree_are_skipped(self, session: AsyncSession):
        account_id, _ = await _seed_setup(session)
        cat_svc = CategoryService(session)
        await cat_svc.ensure_subscriptions_root_and_children()
        root = await cat_svc.get_subscriptions_root()
        assert root is not None
        payee = await _add_payee(session, "Domena")
        for date in (datetime.date(2025, 5, 1), datetime.date(2026, 5, 1)):
            await _add_expense(
                session,
                account_id=account_id,
                category_id=root.id,
                payee_id=payee.id,
                amount=Decimal("120.00"),
                date=date,
            )

        assert await UnplannedRadarService(session).detect(today=TODAY) == []

    async def test_candidates_are_ordered_by_yearly_cost(self, session: AsyncSession):
        account_id, category_id, _ = await _seed_yearly_car_service(session)
        small = await _add_payee(session, "Kominiarz")
        for date in (datetime.date(2025, 2, 1), datetime.date(2026, 2, 1)):
            await _add_expense(
                session,
                account_id=account_id,
                category_id=category_id,
                payee_id=small.id,
                amount=Decimal("150.00"),
                date=date,
            )

        candidates = await UnplannedRadarService(session).detect(today=TODAY)

        assert [c.source_name for c in candidates] == ["Serwis Auto", "Kominiarz"]


# ── Summary ──────────────────────────────────────────────────────────────────


class TestSummary:
    async def test_summary_totals_the_yearly_estimates(self, session: AsyncSession):
        account_id, category_id, _ = await _seed_yearly_car_service(session)
        payee = await _add_payee(session, "Kominiarz")
        for date in (datetime.date(2025, 2, 1), datetime.date(2026, 2, 1)):
            await _add_expense(
                session,
                account_id=account_id,
                category_id=category_id,
                payee_id=payee.id,
                amount=Decimal("150.00"),
                date=date,
            )

        candidates = await UnplannedRadarService(session).detect(today=TODAY)
        summary = summarise(candidates)

        assert summary.candidate_count == 2
        assert summary.yearly_total == Decimal("1450.00")
        assert summary.monthly_equivalent == Decimal("120.83")

    def test_summary_of_nothing_is_zero(self):
        summary = summarise([])

        assert summary.candidate_count == 0
        assert summary.yearly_total == Decimal("0.00")
        assert summary.monthly_equivalent == Decimal("0.00")


# ── Dismissal ────────────────────────────────────────────────────────────────


class TestDismiss:
    async def test_dismissed_candidate_does_not_return(self, session: AsyncSession):
        await _seed_yearly_car_service(session)
        svc = UnplannedRadarService(session)
        [candidate] = await svc.detect(today=TODAY)

        await svc.dismiss(candidate)

        assert await svc.detect(today=TODAY) == []

    async def test_dismissing_twice_is_idempotent(self, session: AsyncSession):
        await _seed_yearly_car_service(session)
        svc = UnplannedRadarService(session)
        [candidate] = await svc.detect(today=TODAY)

        await svc.dismiss(candidate)
        await svc.dismiss(candidate)

        assert await svc.detect(today=TODAY) == []

    async def test_radar_dismissal_does_not_silence_the_subscription_detector(
        self, session: AsyncSession
    ):
        account_id, category_id = await _seed_setup(session)
        payee = await _add_payee(session, "Serwis Auto")
        # Yearly charges the radar picks up …
        await _add_expense(
            session,
            account_id=account_id,
            category_id=category_id,
            payee_id=payee.id,
            amount=Decimal("1300.00"),
            date=datetime.date(2024, 9, 10),
        )
        await _add_expense(
            session,
            account_id=account_id,
            category_id=category_id,
            payee_id=payee.id,
            amount=Decimal("1300.00"),
            date=datetime.date(2025, 9, 10),
        )
        radar = UnplannedRadarService(session)
        [candidate] = await radar.detect(today=TODAY)
        await radar.dismiss(candidate)

        # … the same payee is still a subscription candidate (365-day cadence).
        sub_candidates = await SubscriptionService(session).detect_candidates(today=TODAY)

        assert [c.payee_name for c in sub_candidates] == ["Serwis Auto"]
        assert await SubscriptionService(session).list_dismissed() == []


# ── Conversion ───────────────────────────────────────────────────────────────


class TestCreatePlannedFromCandidate:
    async def test_creates_a_planned_transaction_from_the_candidate(self, session: AsyncSession):
        account_id, category_id, _ = await _seed_yearly_car_service(session)
        svc = UnplannedRadarService(session)
        [candidate] = await svc.detect(today=TODAY)

        planned = await svc.create_planned_from_candidate(candidate)

        assert planned.name == "Serwis Auto"
        assert planned.amount == Decimal("1300.00")
        assert planned.type == TransactionType.EXPENSE
        assert planned.account_id == account_id
        assert planned.category_id == category_id
        assert planned.frequency == RecurrenceFrequency.YEARLY
        assert planned.interval == 1
        assert planned.start_date == datetime.date(2026, 9, 10)
        assert planned.is_active is True

    async def test_overrides_win_over_candidate_defaults(self, session: AsyncSession):
        await _seed_yearly_car_service(session)
        other = await AccountService(session).create(
            AccountCreate(name="Savings", type=AccountType.SAVINGS, balance=Decimal("0"))
        )
        other_cat = await CategoryService(session).create(
            CategoryCreate(name="Maintenance", type=CategoryType.EXPENSE)
        )
        svc = UnplannedRadarService(session)
        [candidate] = await svc.detect(today=TODAY)

        planned = await svc.create_planned_from_candidate(
            candidate,
            account_id=other.id,
            category_id=other_cat.id,
            amount=Decimal("1500.00"),
            start_date=datetime.date(2026, 10, 1),
            name="Serwis + opony",
        )

        assert planned.account_id == other.id
        assert planned.category_id == other_cat.id
        assert planned.amount == Decimal("1500.00")
        assert planned.start_date == datetime.date(2026, 10, 1)
        assert planned.name == "Serwis + opony"

    async def test_source_charges_are_linked_to_the_new_plan(self, session: AsyncSession):
        await _seed_yearly_car_service(session)
        svc = UnplannedRadarService(session)
        [candidate] = await svc.detect(today=TODAY)

        planned = await svc.create_planned_from_candidate(candidate)

        linked = await session.execute(
            select(Transaction.date)
            .where(Transaction.planned_transaction_id == planned.id)
            .order_by(Transaction.date)
        )
        assert list(linked.scalars().all()) == [
            datetime.date(2024, 9, 10),
            datetime.date(2025, 9, 10),
        ]
        assert await svc.linked_history(planned.id) == [
            datetime.date(2024, 9, 10),
            datetime.date(2025, 9, 10),
        ]

    async def test_converted_candidate_stops_being_detected(self, session: AsyncSession):
        await _seed_yearly_car_service(session)
        svc = UnplannedRadarService(session)
        [candidate] = await svc.detect(today=TODAY)

        await svc.create_planned_from_candidate(candidate)

        assert await svc.detect(today=TODAY) == []

    async def test_planned_with_history_reports_the_link_count(self, session: AsyncSession):
        await _seed_yearly_car_service(session)
        svc = UnplannedRadarService(session)
        [candidate] = await svc.detect(today=TODAY)
        planned = await svc.create_planned_from_candidate(candidate)

        [row] = await svc.planned_with_history()

        assert row.planned_id == planned.id
        assert row.name == "Serwis Auto"
        assert row.linked_count == 2
        assert row.linked_dates == [
            datetime.date(2024, 9, 10),
            datetime.date(2025, 9, 10),
        ]

    async def test_blank_name_is_rejected(self, session: AsyncSession):
        from kaleta.exceptions import ValidationError

        await _seed_yearly_car_service(session)
        svc = UnplannedRadarService(session)
        [candidate] = await svc.detect(today=TODAY)

        with pytest.raises(ValidationError):
            await svc.create_planned_from_candidate(candidate, name="   ")

    async def test_linked_history_of_an_unknown_plan_raises(self, session: AsyncSession):
        from kaleta.exceptions import NotFoundError

        with pytest.raises(NotFoundError):
            await UnplannedRadarService(session).linked_history(999)
