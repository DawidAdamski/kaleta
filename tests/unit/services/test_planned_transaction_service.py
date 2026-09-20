# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for PlannedTransactionService — uses in-memory SQLite.

Note: The PlannedTransaction model does not have `occurrence_limit` or
`destination_account_id` fields. Tests for those concepts are omitted.
Transfers (income/expense) are tested via TransactionType.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.account import AccountType
from kaleta.models.category import CategoryType
from kaleta.models.planned_transaction import RecurrenceFrequency
from kaleta.models.transaction import TransactionType
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.category import CategoryCreate
from kaleta.schemas.planned_transaction import PlannedTransactionCreate, PlannedTransactionUpdate
from kaleta.services import AccountService, CategoryService, PlannedTransactionService

# ── Fixtures & helpers ─────────────────────────────────────────────────────────


@pytest.fixture
def svc(session: AsyncSession) -> PlannedTransactionService:
    return PlannedTransactionService(session)


async def _make_account(session: AsyncSession, name: str = "Checking") -> int:
    acc = await AccountService(session).create(AccountCreate(name=name, type=AccountType.CHECKING))
    return acc.id


async def _make_category(
    session: AsyncSession,
    name: str = "Bills",
    cat_type: CategoryType = CategoryType.EXPENSE,
) -> int:
    cat = await CategoryService(session).create(CategoryCreate(name=name, type=cat_type))
    return cat.id


def _pt(account_id: int, **kwargs) -> PlannedTransactionCreate:
    defaults: dict = dict(
        name="Rent",
        amount=Decimal("1000.00"),
        type=TransactionType.EXPENSE,
        account_id=account_id,
        frequency=RecurrenceFrequency.MONTHLY,
        start_date=datetime.date(2025, 1, 1),
    )
    defaults.update(kwargs)
    return PlannedTransactionCreate(**defaults)


# ── Create ─────────────────────────────────────────────────────────────────────


class TestPlannedTransactionCreate:
    async def test_create_monthly_returns_object_with_id(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        pt = await svc.create(_pt(acc_id, frequency=RecurrenceFrequency.MONTHLY))
        assert pt.id is not None
        assert pt.name == "Rent"
        assert pt.frequency == RecurrenceFrequency.MONTHLY
        assert pt.amount == Decimal("1000.00")

    async def test_create_weekly(self, svc: PlannedTransactionService, session: AsyncSession):
        acc_id = await _make_account(session)
        pt = await svc.create(_pt(acc_id, name="Groceries", frequency=RecurrenceFrequency.WEEKLY))
        assert pt.frequency == RecurrenceFrequency.WEEKLY

    async def test_create_yearly(self, svc: PlannedTransactionService, session: AsyncSession):
        acc_id = await _make_account(session)
        pt = await svc.create(_pt(acc_id, name="Insurance", frequency=RecurrenceFrequency.YEARLY))
        assert pt.frequency == RecurrenceFrequency.YEARLY

    async def test_create_with_end_date(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        end = datetime.date(2025, 12, 31)
        pt = await svc.create(_pt(acc_id, end_date=end))
        assert pt.end_date == end

    async def test_create_without_end_date_is_open_ended(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        pt = await svc.create(_pt(acc_id))
        assert pt.end_date is None

    async def test_create_as_transfer_type_income(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        """Income type can be used to represent a recurring transfer in."""
        src_id = await _make_account(session, name="Source")
        pt = await svc.create(
            _pt(
                src_id,
                name="Salary",
                type=TransactionType.INCOME,
                frequency=RecurrenceFrequency.MONTHLY,
            )
        )
        assert pt.type == TransactionType.INCOME
        assert pt.account_id == src_id

    async def test_create_as_transfer_type_expense(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        """Expense type on a second account represents the destination side of a transfer."""
        dst_id = await _make_account(session, name="Destination")
        pt = await svc.create(
            _pt(
                dst_id,
                name="Savings Transfer",
                type=TransactionType.EXPENSE,
                frequency=RecurrenceFrequency.MONTHLY,
            )
        )
        assert pt.type == TransactionType.EXPENSE
        assert pt.account_id == dst_id

    async def test_create_with_category(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        cat_id = await _make_category(session)
        pt = await svc.create(_pt(acc_id, category_id=cat_id))
        assert pt.category_id == cat_id

    async def test_create_is_active_by_default(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        pt = await svc.create(_pt(acc_id))
        assert pt.is_active is True


# ── Read ───────────────────────────────────────────────────────────────────────


class TestPlannedTransactionRead:
    async def test_get_nonexistent_returns_none(self, svc: PlannedTransactionService):
        assert await svc.get(99999) is None

    async def test_get_existing_returns_object(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        created = await svc.create(_pt(acc_id))
        fetched = await svc.get(created.id)
        assert fetched is not None
        assert fetched.id == created.id

    async def test_list_returns_all_created(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        await svc.create(_pt(acc_id, name="A"))
        await svc.create(_pt(acc_id, name="B"))
        result = await svc.list()
        assert len(result) == 2


# ── Toggle active ──────────────────────────────────────────────────────────────


class TestPlannedTransactionToggleActive:
    async def test_toggle_active_to_inactive(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        pt = await svc.create(_pt(acc_id))
        assert pt.is_active is True
        toggled = await svc.toggle_active(pt.id)
        assert toggled is not None
        assert toggled.is_active is False

    async def test_toggle_inactive_to_active(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        pt = await svc.create(_pt(acc_id, is_active=False))
        toggled = await svc.toggle_active(pt.id)
        assert toggled is not None
        assert toggled.is_active is True

    async def test_toggle_nonexistent_returns_none(self, svc: PlannedTransactionService):
        assert await svc.toggle_active(99999) is None

    async def test_double_toggle_restores_original_state(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        pt = await svc.create(_pt(acc_id))
        await svc.toggle_active(pt.id)
        restored = await svc.toggle_active(pt.id)
        assert restored is not None
        assert restored.is_active is True


# ── List filtering ─────────────────────────────────────────────────────────────


class TestPlannedTransactionList:
    async def test_list_returns_active_and_inactive(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        """list() without filtering returns all records regardless of is_active."""
        acc_id = await _make_account(session)
        await svc.create(_pt(acc_id, name="Active", is_active=True))
        await svc.create(_pt(acc_id, name="Inactive", is_active=False))
        result = await svc.list()
        assert len(result) == 2

    async def test_list_active_only_via_get_occurrences(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        """get_occurrences(active_only=True) excludes inactive planned transactions."""
        acc_id = await _make_account(session)
        start = datetime.date(2025, 1, 1)
        end = datetime.date(2025, 12, 31)

        await svc.create(
            _pt(acc_id, name="Active", is_active=True, start_date=datetime.date(2025, 6, 1))
        )
        inactive = await svc.create(
            _pt(acc_id, name="Inactive", is_active=True, start_date=datetime.date(2025, 6, 1))
        )
        await svc.toggle_active(inactive.id)

        active_occs = await svc.get_occurrences(start, end, active_only=True)
        all_occs = await svc.get_occurrences(start, end, active_only=False)

        active_names = {o.name for o in active_occs}
        all_names = {o.name for o in all_occs}

        assert "Active" in active_names
        assert "Inactive" not in active_names
        assert "Inactive" in all_names


# ── Update ─────────────────────────────────────────────────────────────────────


class TestPlannedTransactionUpdate:
    async def test_update_nonexistent_returns_none(self, svc: PlannedTransactionService):
        assert await svc.update(99999, PlannedTransactionUpdate(name="x")) is None

    async def test_update_name(self, svc: PlannedTransactionService, session: AsyncSession):
        acc_id = await _make_account(session)
        pt = await svc.create(_pt(acc_id))
        updated = await svc.update(pt.id, PlannedTransactionUpdate(name="New Name"))
        assert updated is not None
        assert updated.name == "New Name"


# ── Delete ─────────────────────────────────────────────────────────────────────


class TestPlannedTransactionDelete:
    async def test_delete_existing(self, svc: PlannedTransactionService, session: AsyncSession):
        acc_id = await _make_account(session)
        pt = await svc.create(_pt(acc_id))
        assert await svc.delete(pt.id) is True
        assert await svc.get(pt.id) is None

    async def test_delete_nonexistent(self, svc: PlannedTransactionService):
        assert await svc.delete(99999) is False


# ── Occurrence generation ──────────────────────────────────────────────────────


class TestGetOccurrences:
    async def test_monthly_generates_multiple_occurrences(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        await svc.create(
            _pt(
                acc_id,
                frequency=RecurrenceFrequency.MONTHLY,
                start_date=datetime.date(2025, 1, 1),
            )
        )
        occs = await svc.get_occurrences(datetime.date(2025, 1, 1), datetime.date(2025, 6, 30))
        # Should have occurrences in Feb, Mar, Apr, May, Jun (5) since start=Jan 1
        # and we need dates strictly advancing from start_date into the window
        assert len(occs) >= 2

    async def test_weekly_generates_more_occurrences_than_monthly(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        await svc.create(
            _pt(
                acc_id,
                name="Weekly",
                frequency=RecurrenceFrequency.WEEKLY,
                start_date=datetime.date(2025, 1, 1),
            )
        )
        await svc.create(
            _pt(
                acc_id,
                name="Monthly",
                frequency=RecurrenceFrequency.MONTHLY,
                start_date=datetime.date(2025, 1, 1),
            )
        )
        occs = await svc.get_occurrences(datetime.date(2025, 1, 1), datetime.date(2025, 3, 31))
        weekly = [o for o in occs if o.name == "Weekly"]
        monthly = [o for o in occs if o.name == "Monthly"]
        assert len(weekly) > len(monthly)

    async def test_end_date_limits_occurrences(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        await svc.create(
            _pt(
                acc_id,
                frequency=RecurrenceFrequency.MONTHLY,
                start_date=datetime.date(2025, 1, 1),
                end_date=datetime.date(2025, 3, 31),
            )
        )
        occs = await svc.get_occurrences(datetime.date(2025, 1, 1), datetime.date(2025, 12, 31))
        # No occurrence should fall after March 31
        for occ in occs:
            assert occ.date <= datetime.date(2025, 3, 31)

    async def test_occurrences_sorted_by_date(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        await svc.create(
            _pt(acc_id, frequency=RecurrenceFrequency.MONTHLY, start_date=datetime.date(2025, 1, 1))
        )
        occs = await svc.get_occurrences(datetime.date(2025, 1, 1), datetime.date(2025, 6, 30))
        dates = [o.date for o in occs]
        assert dates == sorted(dates)


# ── Payment Calendar grid ──────────────────────────────────────────────────────


class TestGridForMonth:
    async def test_empty_month_returns_no_days(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        await svc.create(_pt(acc_id, start_date=datetime.date(2030, 1, 1)))
        grid = await svc.grid_for_month(2025, 6)
        assert grid.year == 2025 and grid.month == 6
        assert grid.days == {}
        assert grid.overdue == []

    async def test_single_once_occurrence_populates_one_day(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        await svc.create(
            _pt(
                acc_id,
                name="Rent",
                frequency=RecurrenceFrequency.ONCE,
                start_date=datetime.date(2025, 6, 10),
                amount=Decimal("1500.00"),
                type=TransactionType.EXPENSE,
            )
        )
        grid = await svc.grid_for_month(2025, 6)
        day = grid.days[datetime.date(2025, 6, 10)]
        assert day.outflow == Decimal("1500.00")
        assert day.inflow == Decimal("0")
        assert day.net == Decimal("-1500.00")
        assert len(day.occurrences) == 1

    async def test_multiple_plans_same_day_aggregate(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        d = datetime.date(2025, 6, 15)
        await svc.create(
            _pt(
                acc_id,
                name="Salary",
                frequency=RecurrenceFrequency.ONCE,
                start_date=d,
                amount=Decimal("5000"),
                type=TransactionType.INCOME,
            )
        )
        await svc.create(
            _pt(
                acc_id,
                name="Rent",
                frequency=RecurrenceFrequency.ONCE,
                start_date=d,
                amount=Decimal("1500"),
                type=TransactionType.EXPENSE,
            )
        )
        await svc.create(
            _pt(
                acc_id,
                name="Internet",
                frequency=RecurrenceFrequency.ONCE,
                start_date=d,
                amount=Decimal("100"),
                type=TransactionType.EXPENSE,
            )
        )
        grid = await svc.grid_for_month(2025, 6)
        cell = grid.days[d]
        assert cell.inflow == Decimal("5000")
        assert cell.outflow == Decimal("1600")
        assert cell.net == Decimal("3400")
        assert len(cell.occurrences) == 3

    async def test_monthly_recurrence_hits_month(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        await svc.create(
            _pt(
                acc_id,
                name="Rent",
                frequency=RecurrenceFrequency.MONTHLY,
                start_date=datetime.date(2025, 1, 1),
            )
        )
        grid = await svc.grid_for_month(2025, 6)
        assert datetime.date(2025, 6, 1) in grid.days

    async def test_overdue_bucket_picks_up_prior_month(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        await svc.create(
            _pt(
                acc_id,
                name="Missed Bill",
                frequency=RecurrenceFrequency.ONCE,
                start_date=datetime.date(2025, 5, 20),
                amount=Decimal("200"),
                type=TransactionType.EXPENSE,
            )
        )
        grid = await svc.grid_for_month(2025, 6, overdue_window_days=30)
        assert any(o.name == "Missed Bill" for o in grid.overdue)
        assert grid.days == {}

    async def test_overdue_window_respected(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        await svc.create(
            _pt(
                acc_id,
                name="Ancient",
                frequency=RecurrenceFrequency.ONCE,
                start_date=datetime.date(2025, 1, 10),
                type=TransactionType.EXPENSE,
            )
        )
        grid = await svc.grid_for_month(2025, 6, overdue_window_days=30)
        assert grid.overdue == []

    async def test_active_only_excludes_paused(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        paused = await svc.create(
            _pt(
                acc_id,
                name="Paused",
                frequency=RecurrenceFrequency.ONCE,
                start_date=datetime.date(2025, 6, 10),
            )
        )
        await svc.toggle_active(paused.id)
        grid = await svc.grid_for_month(2025, 6, active_only=True)
        assert grid.days == {}
        grid_all = await svc.grid_for_month(2025, 6, active_only=False)
        assert datetime.date(2025, 6, 10) in grid_all.days

    async def test_account_filter(self, svc: PlannedTransactionService, session: AsyncSession):
        a1 = await _make_account(session, name="A1")
        a2 = await _make_account(session, name="A2")
        await svc.create(
            _pt(
                a1,
                name="On A1",
                frequency=RecurrenceFrequency.ONCE,
                start_date=datetime.date(2025, 6, 5),
            )
        )
        await svc.create(
            _pt(
                a2,
                name="On A2",
                frequency=RecurrenceFrequency.ONCE,
                start_date=datetime.date(2025, 6, 5),
            )
        )
        grid = await svc.grid_for_month(2025, 6, account_id=a1)
        cell = grid.days[datetime.date(2025, 6, 5)]
        assert [o.name for o in cell.occurrences] == ["On A1"]

    async def test_totals_across_month(self, svc: PlannedTransactionService, session: AsyncSession):
        acc_id = await _make_account(session)
        await svc.create(
            _pt(
                acc_id,
                name="Salary",
                frequency=RecurrenceFrequency.ONCE,
                start_date=datetime.date(2025, 6, 1),
                amount=Decimal("5000"),
                type=TransactionType.INCOME,
            )
        )
        await svc.create(
            _pt(
                acc_id,
                name="Rent",
                frequency=RecurrenceFrequency.ONCE,
                start_date=datetime.date(2025, 6, 5),
                amount=Decimal("1500"),
                type=TransactionType.EXPENSE,
            )
        )
        grid = await svc.grid_for_month(2025, 6)
        assert grid.total_inflow() == Decimal("5000")
        assert grid.total_outflow() == Decimal("1500")
        assert grid.total_net() == Decimal("3500")


# ── Posting due occurrences ───────────────────────────────────────────────────


class TestPostOccurrence:
    async def test_post_creates_linked_transaction(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        """Covers: KAL-PLN-015"""
        acc_id = await _make_account(session, name="PKO Main")
        pt = await svc.create(
            _pt(
                acc_id,
                name="Netflix",
                amount=Decimal("49.00"),
                frequency=RecurrenceFrequency.MONTHLY,
                start_date=datetime.date(2025, 1, 15),
            )
        )
        tx = await svc.post_occurrence(pt.id, datetime.date(2025, 1, 15))
        assert tx.amount == Decimal("49.00")
        assert tx.date == datetime.date(2025, 1, 15)
        assert tx.account_id == acc_id
        assert tx.planned_transaction_id == pt.id
        assert tx.description == "Netflix"

    async def test_repost_is_idempotent(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        """Covers: KAL-PLN-017"""
        acc_id = await _make_account(session, name="PKO Main")
        pt = await svc.create(
            _pt(
                acc_id,
                name="Rent",
                amount=Decimal("2500.00"),
                frequency=RecurrenceFrequency.MONTHLY,
                start_date=datetime.date(2025, 1, 1),
            )
        )
        first = await svc.post_occurrence(pt.id, datetime.date(2025, 1, 1))
        second = await svc.post_occurrence(pt.id, datetime.date(2025, 1, 1))
        assert first.id == second.id
        from sqlalchemy import func, select

        from kaleta.models.transaction import Transaction

        count = await session.scalar(
            select(func.count())
            .select_from(Transaction)
            .where(
                Transaction.planned_transaction_id == pt.id,
                Transaction.date == datetime.date(2025, 1, 1),
            )
        )
        assert count == 1


class TestPostOccurrences:
    """The overdue strip on the Payment Calendar posts the list it drew."""

    async def test_it_posts_the_list_it_was_given_and_no_more(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        """Covers: KAL-PLN-020

        `post_due` would take the whole window; this takes two of its four
        occurrences, which is what a button labelled "Post 2" has to do.
        """
        acc_id = await _make_account(session, name="PKO Main")
        pt = await svc.create(
            _pt(
                acc_id,
                name="Groceries",
                amount=Decimal("300.00"),
                frequency=RecurrenceFrequency.WEEKLY,
                start_date=datetime.date(2025, 1, 1),
            )
        )
        window = await svc.get_occurrences(
            datetime.date(2025, 1, 1),
            datetime.date(2025, 1, 22),
            exclude_posted=True,
        )
        assert len(window) == 4

        posted = await svc.post_occurrences(window[:2])

        assert len(posted) == 2
        assert {tx.date for tx in posted} == {
            datetime.date(2025, 1, 1),
            datetime.date(2025, 1, 8),
        }
        assert all(tx.planned_transaction_id == pt.id for tx in posted)
        left = await svc.get_occurrences(
            datetime.date(2025, 1, 1),
            datetime.date(2025, 1, 22),
            exclude_posted=True,
        )
        assert {o.date for o in left} == {
            datetime.date(2025, 1, 15),
            datetime.date(2025, 1, 22),
        }

    async def test_reposting_the_same_list_creates_nothing_new(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        """Covers: KAL-PLN-017"""
        acc_id = await _make_account(session)
        pt = await svc.create(
            _pt(
                acc_id,
                name="Rent",
                amount=Decimal("2500.00"),
                frequency=RecurrenceFrequency.MONTHLY,
                start_date=datetime.date(2025, 1, 1),
            )
        )
        window = await svc.get_occurrences(
            datetime.date(2025, 1, 1),
            datetime.date(2025, 1, 31),
            exclude_posted=True,
        )
        first = await svc.post_occurrences(window)
        again = await svc.post_occurrences(window)
        assert [tx.id for tx in first] == [tx.id for tx in again]
        assert all(tx.planned_transaction_id == pt.id for tx in first)

    async def test_an_empty_list_posts_nothing(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        assert await svc.post_occurrences([]) == []


class TestPostDue:
    async def test_post_all_due_posts_weekly_window(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        """Covers: KAL-PLN-016"""
        acc_id = await _make_account(session, name="PKO Main")
        pt = await svc.create(
            _pt(
                acc_id,
                name="Groceries",
                amount=Decimal("300.00"),
                frequency=RecurrenceFrequency.WEEKLY,
                start_date=datetime.date(2025, 1, 1),
            )
        )
        posted = await svc.post_due(
            as_of=datetime.date(2025, 1, 15),
            lookback_days=30,
        )
        assert len(posted) == 3
        assert all(tx.planned_transaction_id == pt.id for tx in posted)
        assert {tx.date for tx in posted} == {
            datetime.date(2025, 1, 1),
            datetime.date(2025, 1, 8),
            datetime.date(2025, 1, 15),
        }

    async def test_post_due_skips_already_posted(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        """Covers: KAL-PLN-017"""
        acc_id = await _make_account(session)
        pt = await svc.create(
            _pt(
                acc_id,
                name="Rent",
                amount=Decimal("2500.00"),
                frequency=RecurrenceFrequency.MONTHLY,
                start_date=datetime.date(2025, 1, 1),
            )
        )
        await svc.post_occurrence(pt.id, datetime.date(2025, 1, 1))
        again = await svc.post_due(
            as_of=datetime.date(2025, 1, 10),
            lookback_days=30,
            planned_id=pt.id,
        )
        assert again == []

    async def test_posted_occurrence_leaves_overdue_bucket(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        pt = await svc.create(
            _pt(
                acc_id,
                name="Netflix",
                amount=Decimal("49.00"),
                frequency=RecurrenceFrequency.ONCE,
                start_date=datetime.date(2025, 5, 20),
            )
        )
        grid_before = await svc.grid_for_month(2025, 6, overdue_window_days=30)
        assert any(o.planned_id == pt.id for o in grid_before.overdue)
        await svc.post_occurrence(pt.id, datetime.date(2025, 5, 20))
        grid_after = await svc.grid_for_month(2025, 6, overdue_window_days=30)
        assert not any(o.planned_id == pt.id for o in grid_after.overdue)


# ── Upcoming rows for the ledger ───────────────────────────────────────────────


class TestUpcomingForLedger:
    """Covers: KAL-PLN-011, KAL-PLN-021"""

    async def test_the_window_holds_only_what_falls_inside_it(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        await svc.create(
            _pt(
                acc_id,
                name="Rent",
                frequency=RecurrenceFrequency.MONTHLY,
                start_date=datetime.date(2026, 3, 5),
            )
        )
        occs = await svc.upcoming_for_ledger(datetime.date(2026, 3, 3), datetime.date(2026, 3, 10))
        assert [o.date for o in occs] == [datetime.date(2026, 3, 5)]

    async def test_the_wider_window_shows_the_repeats_the_narrow_one_cuts_off(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        await svc.create(
            _pt(
                acc_id,
                name="Groceries",
                frequency=RecurrenceFrequency.WEEKLY,
                start_date=datetime.date(2026, 3, 13),
            )
        )
        seven = await svc.upcoming_for_ledger(
            datetime.date(2026, 3, 10), datetime.date(2026, 3, 17)
        )
        thirty = await svc.upcoming_for_ledger(
            datetime.date(2026, 3, 10), datetime.date(2026, 4, 9)
        )

        assert [o.date for o in seven] == [datetime.date(2026, 3, 13)]
        assert [o.date for o in thirty] == [
            datetime.date(2026, 3, 13),
            datetime.date(2026, 3, 20),
            datetime.date(2026, 3, 27),
            datetime.date(2026, 4, 3),
        ]

    async def test_an_inverted_window_asks_the_database_for_nothing(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        await svc.create(_pt(acc_id, start_date=datetime.date(2026, 3, 5)))
        assert (
            await svc.upcoming_for_ledger(datetime.date(2026, 3, 10), datetime.date(2026, 3, 3))
            == []
        )

    async def test_the_account_filter_hides_another_account_s_plan(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        mine = await _make_account(session, "PKO Main")
        theirs = await _make_account(session, "mBank Savings")
        await svc.create(_pt(mine, name="Mine", start_date=datetime.date(2026, 3, 5)))
        await svc.create(_pt(theirs, name="Theirs", start_date=datetime.date(2026, 3, 6)))

        occs = await svc.upcoming_for_ledger(
            datetime.date(2026, 3, 1),
            datetime.date(2026, 3, 31),
            account_ids=[mine],
        )
        assert [o.name for o in occs] == ["Mine"]

    async def test_the_type_filter_keeps_only_its_own_kind(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        await svc.create(
            _pt(
                acc_id,
                name="Salary",
                type=TransactionType.INCOME,
                start_date=datetime.date(2026, 3, 5),
            )
        )
        await svc.create(
            _pt(
                acc_id,
                name="Rent",
                type=TransactionType.EXPENSE,
                start_date=datetime.date(2026, 3, 6),
            )
        )

        occs = await svc.upcoming_for_ledger(
            datetime.date(2026, 3, 1),
            datetime.date(2026, 3, 31),
            tx_types=[TransactionType.INCOME],
        )
        assert [o.name for o in occs] == ["Salary"]

    async def test_the_search_matches_the_plan_name_case_insensitively(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        await svc.create(_pt(acc_id, name="Netflix", start_date=datetime.date(2026, 3, 5)))
        await svc.create(_pt(acc_id, name="Rent", start_date=datetime.date(2026, 3, 6)))

        occs = await svc.upcoming_for_ledger(
            datetime.date(2026, 3, 1),
            datetime.date(2026, 3, 31),
            search="netfl",
        )
        assert [o.name for o in occs] == ["Netflix"]

    async def test_an_inactive_plan_never_reaches_the_ledger(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        await svc.create(
            _pt(acc_id, name="Paused", is_active=False, start_date=datetime.date(2026, 3, 5))
        )
        assert (
            await svc.upcoming_for_ledger(datetime.date(2026, 3, 1), datetime.date(2026, 3, 31))
            == []
        )

    async def test_an_occurrence_already_posted_is_not_promised_again(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        plan = await svc.create(_pt(acc_id, name="Rent", start_date=datetime.date(2026, 3, 5)))
        await svc.post_occurrence(plan.id, datetime.date(2026, 3, 5))

        occs = await svc.upcoming_for_ledger(datetime.date(2026, 3, 1), datetime.date(2026, 3, 31))
        assert occs == []


class TestBuildUpcomingRows:
    """Covers: KAL-PLN-011"""

    async def test_a_row_carries_the_marks_that_tell_it_from_a_record(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session, "PKO Main")
        cat_id = await _make_category(session, "Bills")
        await svc.create(
            _pt(
                acc_id,
                name="Rent",
                amount=Decimal("2500.00"),
                category_id=cat_id,
                start_date=datetime.date(2026, 3, 13),
                frequency=RecurrenceFrequency.WEEKLY,
            )
        )
        occs = await svc.upcoming_for_ledger(datetime.date(2026, 3, 10), datetime.date(2026, 3, 17))
        rows = PlannedTransactionService.build_upcoming_rows(occs, datetime.date(2026, 3, 10))

        assert len(rows) == 1
        row = rows[0]
        assert row["is_planned"] is True
        assert row["days_ahead"] == 3
        assert row["date"] == "2026-03-13"
        assert row["date_short"] == "13.03"
        assert row["account"] == "PKO Main"
        assert row["description"] == "Rent"
        assert row["category"] == "Bills"
        assert row["amount"] == "-2,500.00"
        assert row["tags_data"] == []

    async def test_the_row_id_can_never_be_mistaken_for_a_transaction_id(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        plan = await svc.create(_pt(acc_id, start_date=datetime.date(2026, 3, 13)))
        occs = await svc.upcoming_for_ledger(datetime.date(2026, 3, 10), datetime.date(2026, 3, 17))
        rows = PlannedTransactionService.build_upcoming_rows(occs, datetime.date(2026, 3, 10))

        assert rows[0]["id"] == f"planned:{plan.id}:2026-03-13"
        assert rows[0]["planned_id"] == plan.id

    async def test_a_plan_with_no_category_shows_an_em_dash(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        await svc.create(_pt(acc_id, start_date=datetime.date(2026, 3, 13)))
        occs = await svc.upcoming_for_ledger(datetime.date(2026, 3, 10), datetime.date(2026, 3, 17))
        rows = PlannedTransactionService.build_upcoming_rows(occs, datetime.date(2026, 3, 10))
        assert rows[0]["category"] == "—"


WINDOW_TODAY = datetime.date(2026, 3, 10)


class TestUpcomingWindow:
    """Covers: KAL-PLN-011, KAL-PLN-012"""

    def test_off_opens_no_window(self) -> None:
        assert (
            PlannedTransactionService.upcoming_window(
                0, today=WINDOW_TODAY, date_from=None, date_to=None
            )
            is None
        )

    def test_seven_days_runs_from_today_to_the_seventh_day(self) -> None:
        assert PlannedTransactionService.upcoming_window(
            7, today=WINDOW_TODAY, date_from=None, date_to=None
        ) == (
            datetime.date(2026, 3, 10),
            datetime.date(2026, 3, 17),
        )

    def test_thirty_days_runs_to_the_thirtieth_day(self) -> None:
        assert PlannedTransactionService.upcoming_window(
            30, today=WINDOW_TODAY, date_from=None, date_to=None
        ) == (
            datetime.date(2026, 3, 10),
            datetime.date(2026, 4, 9),
        )

    def test_a_later_date_from_moves_the_start(self) -> None:
        assert PlannedTransactionService.upcoming_window(
            30,
            today=WINDOW_TODAY,
            date_from=datetime.date(2026, 3, 20),
            date_to=None,
        ) == (datetime.date(2026, 3, 20), datetime.date(2026, 4, 9))

    def test_a_date_from_in_the_past_does_not_open_the_window_backwards(self) -> None:
        assert PlannedTransactionService.upcoming_window(
            7,
            today=WINDOW_TODAY,
            date_from=datetime.date(2026, 1, 1),
            date_to=None,
        ) == (WINDOW_TODAY, datetime.date(2026, 3, 17))

    def test_an_earlier_date_to_clips_the_end(self) -> None:
        assert PlannedTransactionService.upcoming_window(
            30,
            today=WINDOW_TODAY,
            date_from=None,
            date_to=datetime.date(2026, 3, 12),
        ) == (WINDOW_TODAY, datetime.date(2026, 3, 12))

    def test_a_range_that_ends_in_the_past_opens_nothing(self) -> None:
        assert (
            PlannedTransactionService.upcoming_window(
                7,
                today=WINDOW_TODAY,
                date_from=None,
                date_to=datetime.date(2026, 2, 1),
            )
            is None
        )


class TestPlannedRowKey:
    """Covers: KAL-PLN-022"""

    def test_the_key_round_trips(self) -> None:
        key = PlannedTransactionService.planned_row_key(9, datetime.date(2026, 3, 13))
        assert key == "planned:9:2026-03-13"
        assert PlannedTransactionService.parse_planned_row_key(key) == (
            9,
            datetime.date(2026, 3, 13),
        )

    @pytest.mark.parametrize(
        "row_key",
        [
            17,
            None,
            "17",
            "planned:9",
            "planned:9:2026-03-13:extra",
            "tx:9:2026-03-13",
            "planned:nine:2026-03-13",
            "planned:9:not-a-date",
        ],
    )
    def test_anything_that_is_not_one_of_ours_comes_back_as_none(self, row_key: object) -> None:
        assert PlannedTransactionService.parse_planned_row_key(row_key) is None
