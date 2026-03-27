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

    async def test_create_weekly(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        pt = await svc.create(_pt(acc_id, name="Groceries", frequency=RecurrenceFrequency.WEEKLY))
        assert pt.frequency == RecurrenceFrequency.WEEKLY

    async def test_create_yearly(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        pt = await svc.create(
            _pt(acc_id, name="Insurance", frequency=RecurrenceFrequency.YEARLY)
        )
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

    async def test_update_name(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        pt = await svc.create(_pt(acc_id))
        updated = await svc.update(pt.id, PlannedTransactionUpdate(name="New Name"))
        assert updated is not None
        assert updated.name == "New Name"


# ── Delete ─────────────────────────────────────────────────────────────────────


class TestPlannedTransactionDelete:

    async def test_delete_existing(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
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
        occs = await svc.get_occurrences(
            datetime.date(2025, 1, 1), datetime.date(2025, 6, 30)
        )
        # Should have occurrences in Feb, Mar, Apr, May, Jun (5) since start=Jan 1
        # and we need dates strictly advancing from start_date into the window
        assert len(occs) >= 2

    async def test_weekly_generates_more_occurrences_than_monthly(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        await svc.create(
            _pt(acc_id, name="Weekly", frequency=RecurrenceFrequency.WEEKLY,
                start_date=datetime.date(2025, 1, 1))
        )
        await svc.create(
            _pt(acc_id, name="Monthly", frequency=RecurrenceFrequency.MONTHLY,
                start_date=datetime.date(2025, 1, 1))
        )
        occs = await svc.get_occurrences(
            datetime.date(2025, 1, 1), datetime.date(2025, 3, 31)
        )
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
        occs = await svc.get_occurrences(
            datetime.date(2025, 1, 1), datetime.date(2025, 12, 31)
        )
        # No occurrence should fall after March 31
        for occ in occs:
            assert occ.date <= datetime.date(2025, 3, 31)

    async def test_occurrences_sorted_by_date(
        self, svc: PlannedTransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        await svc.create(
            _pt(acc_id, frequency=RecurrenceFrequency.MONTHLY,
                start_date=datetime.date(2025, 1, 1))
        )
        occs = await svc.get_occurrences(
            datetime.date(2025, 1, 1), datetime.date(2025, 6, 30)
        )
        dates = [o.date for o in occs]
        assert dates == sorted(dates)
