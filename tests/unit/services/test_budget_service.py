"""Unit tests for BudgetService — uses in-memory SQLite."""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.account import AccountType
from kaleta.models.category import CategoryType
from kaleta.models.transaction import TransactionType
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.budget import BudgetCreate, BudgetUpdate
from kaleta.schemas.category import CategoryCreate
from kaleta.schemas.transaction import TransactionCreate
from kaleta.services import AccountService, BudgetService, CategoryService, TransactionService

# ── Fixtures & helpers ─────────────────────────────────────────────────────────


@pytest.fixture
def svc(session: AsyncSession) -> BudgetService:
    return BudgetService(session)


async def _make_category(
    session: AsyncSession,
    name: str = "Food",
    cat_type: CategoryType = CategoryType.EXPENSE,
) -> int:
    cat = await CategoryService(session).create(CategoryCreate(name=name, type=cat_type))
    return cat.id


async def _make_account(session: AsyncSession, name: str = "Checking") -> int:
    acc = await AccountService(session).create(AccountCreate(name=name, type=AccountType.CHECKING))
    return acc.id


async def _make_expense(
    session: AsyncSession,
    account_id: int,
    category_id: int,
    amount: Decimal,
    date: datetime.date,
) -> None:
    await TransactionService(session).create(
        TransactionCreate(
            account_id=account_id,
            category_id=category_id,
            amount=amount,
            type=TransactionType.EXPENSE,
            date=date,
            description="test expense",
        )
    )


# ── CRUD basics ────────────────────────────────────────────────────────────────


class TestBudgetCreate:
    async def test_create_returns_object_with_id(self, svc: BudgetService, session: AsyncSession):
        cat_id = await _make_category(session)
        budget = await svc.create(
            BudgetCreate(category_id=cat_id, amount=Decimal("500.00"), month=1, year=2025)
        )
        assert budget.id is not None
        assert budget.category_id == cat_id
        assert budget.amount == Decimal("500.00")
        assert budget.month == 1
        assert budget.year == 2025

    async def test_get_nonexistent_returns_none(self, svc: BudgetService):
        assert await svc.get(99999) is None

    async def test_update_nonexistent_returns_none(self, svc: BudgetService):
        assert await svc.update(99999, BudgetUpdate(amount=Decimal("100.00"))) is None

    async def test_delete_existing(self, svc: BudgetService, session: AsyncSession):
        cat_id = await _make_category(session)
        budget = await svc.create(
            BudgetCreate(category_id=cat_id, amount=Decimal("200.00"), month=3, year=2025)
        )
        assert await svc.delete(budget.id) is True
        assert await svc.get(budget.id) is None

    async def test_delete_nonexistent(self, svc: BudgetService):
        assert await svc.delete(99999) is False


class TestBudgetUpsert:
    async def test_upsert_creates_when_missing(self, svc: BudgetService, session: AsyncSession):
        cat_id = await _make_category(session)
        budget = await svc.upsert(
            BudgetCreate(category_id=cat_id, amount=Decimal("300.00"), month=6, year=2025)
        )
        assert budget.id is not None
        assert budget.amount == Decimal("300.00")

    async def test_upsert_updates_when_existing(self, svc: BudgetService, session: AsyncSession):
        cat_id = await _make_category(session)
        b1 = await svc.create(
            BudgetCreate(category_id=cat_id, amount=Decimal("100.00"), month=6, year=2025)
        )
        b2 = await svc.upsert(
            BudgetCreate(category_id=cat_id, amount=Decimal("999.00"), month=6, year=2025)
        )
        # Same record updated, not a new row
        assert b2.id == b1.id
        assert b2.amount == Decimal("999.00")


# ── range_summary ──────────────────────────────────────────────────────────────


class TestRangeSummaryNoData:
    async def test_empty_range_returns_empty_list(self, svc: BudgetService):
        start = datetime.date(2025, 1, 1)
        end = datetime.date(2025, 3, 31)
        result = await svc.range_summary(start, end)
        assert result == []

    async def test_budget_outside_range_not_included(
        self, svc: BudgetService, session: AsyncSession
    ):
        cat_id = await _make_category(session)
        # Budget in December 2024 — outside the queried Jan-Mar 2025 window
        await svc.create(
            BudgetCreate(category_id=cat_id, amount=Decimal("400.00"), month=12, year=2024)
        )
        start = datetime.date(2025, 1, 1)
        end = datetime.date(2025, 3, 31)
        result = await svc.range_summary(start, end)
        assert result == []


class TestRangeSummaryBasic:
    async def test_single_month_budget_no_spending(self, svc: BudgetService, session: AsyncSession):
        cat_id = await _make_category(session)
        await svc.create(
            BudgetCreate(category_id=cat_id, amount=Decimal("500.00"), month=1, year=2025)
        )
        start = datetime.date(2025, 1, 1)
        end = datetime.date(2025, 1, 31)
        result = await svc.range_summary(start, end)

        assert len(result) == 1
        summary = result[0]
        assert summary.category_id == cat_id
        assert summary.budget_amount == Decimal("500.00")
        assert summary.actual_amount == Decimal("0.00")
        assert summary.remaining == Decimal("500.00")
        assert summary.over_budget is False

    async def test_actual_spending_correctly_summed_within_range(
        self, svc: BudgetService, session: AsyncSession
    ):
        cat_id = await _make_category(session)
        acc_id = await _make_account(session)
        await svc.create(
            BudgetCreate(category_id=cat_id, amount=Decimal("1000.00"), month=1, year=2025)
        )

        # Two expenses inside the range
        await _make_expense(session, acc_id, cat_id, Decimal("200.00"), datetime.date(2025, 1, 5))
        await _make_expense(session, acc_id, cat_id, Decimal("350.00"), datetime.date(2025, 1, 20))

        start = datetime.date(2025, 1, 1)
        end = datetime.date(2025, 1, 31)
        result = await svc.range_summary(start, end)

        assert len(result) == 1
        summary = result[0]
        assert summary.actual_amount == Decimal("550.00")
        assert summary.remaining == Decimal("450.00")
        assert summary.over_budget is False

    async def test_expense_outside_range_not_counted(
        self, svc: BudgetService, session: AsyncSession
    ):
        cat_id = await _make_category(session)
        acc_id = await _make_account(session)
        await svc.create(
            BudgetCreate(category_id=cat_id, amount=Decimal("500.00"), month=3, year=2025)
        )

        # Expense in February — before the March range start
        await _make_expense(session, acc_id, cat_id, Decimal("999.00"), datetime.date(2025, 2, 28))

        start = datetime.date(2025, 3, 1)
        end = datetime.date(2025, 3, 31)
        result = await svc.range_summary(start, end)

        assert len(result) == 1
        assert result[0].actual_amount == Decimal("0.00")

    async def test_over_budget_flag(self, svc: BudgetService, session: AsyncSession):
        cat_id = await _make_category(session)
        acc_id = await _make_account(session)
        await svc.create(
            BudgetCreate(category_id=cat_id, amount=Decimal("100.00"), month=4, year=2025)
        )
        await _make_expense(session, acc_id, cat_id, Decimal("150.00"), datetime.date(2025, 4, 10))

        result = await svc.range_summary(datetime.date(2025, 4, 1), datetime.date(2025, 4, 30))
        assert len(result) == 1
        assert result[0].over_budget is True

    async def test_percent_used_calculated_correctly(
        self, svc: BudgetService, session: AsyncSession
    ):
        cat_id = await _make_category(session)
        acc_id = await _make_account(session)
        await svc.create(
            BudgetCreate(category_id=cat_id, amount=Decimal("200.00"), month=5, year=2025)
        )
        await _make_expense(session, acc_id, cat_id, Decimal("50.00"), datetime.date(2025, 5, 1))

        result = await svc.range_summary(datetime.date(2025, 5, 1), datetime.date(2025, 5, 31))
        assert result[0].percent_used == pytest.approx(25.0)


class TestRangeSummaryMultiMonth:
    async def test_budget_amounts_summed_across_months(
        self, svc: BudgetService, session: AsyncSession
    ):
        cat_id = await _make_category(session)
        # Two budget months within the Q1 2025 range
        await svc.create(
            BudgetCreate(category_id=cat_id, amount=Decimal("300.00"), month=1, year=2025)
        )
        await svc.create(
            BudgetCreate(category_id=cat_id, amount=Decimal("400.00"), month=2, year=2025)
        )

        start = datetime.date(2025, 1, 1)
        end = datetime.date(2025, 2, 28)
        result = await svc.range_summary(start, end)

        assert len(result) == 1
        assert result[0].budget_amount == Decimal("700.00")

    async def test_multi_month_spending_aggregated(self, svc: BudgetService, session: AsyncSession):
        cat_id = await _make_category(session)
        acc_id = await _make_account(session)
        await svc.create(
            BudgetCreate(category_id=cat_id, amount=Decimal("500.00"), month=1, year=2025)
        )
        await svc.create(
            BudgetCreate(category_id=cat_id, amount=Decimal("500.00"), month=2, year=2025)
        )

        await _make_expense(session, acc_id, cat_id, Decimal("100.00"), datetime.date(2025, 1, 15))
        await _make_expense(session, acc_id, cat_id, Decimal("200.00"), datetime.date(2025, 2, 10))

        start = datetime.date(2025, 1, 1)
        end = datetime.date(2025, 2, 28)
        result = await svc.range_summary(start, end)

        assert result[0].budget_amount == Decimal("1000.00")
        assert result[0].actual_amount == Decimal("300.00")

    async def test_multiple_categories_sorted_by_name(
        self, svc: BudgetService, session: AsyncSession
    ):
        cat_a = await _make_category(session, name="Aaardvark")
        cat_z = await _make_category(session, name="Zebra")
        await svc.create(
            BudgetCreate(category_id=cat_z, amount=Decimal("100.00"), month=7, year=2025)
        )
        await svc.create(
            BudgetCreate(category_id=cat_a, amount=Decimal("200.00"), month=7, year=2025)
        )

        result = await svc.range_summary(datetime.date(2025, 7, 1), datetime.date(2025, 7, 31))

        assert len(result) == 2
        assert result[0].category_name == "Aaardvark"
        assert result[1].category_name == "Zebra"

    async def test_internal_transfers_excluded_from_actuals(
        self, svc: BudgetService, session: AsyncSession
    ):
        """Internal transfers must not inflate actual spending."""
        cat_id = await _make_category(session)
        acc_id = await _make_account(session)
        await svc.create(
            BudgetCreate(category_id=cat_id, amount=Decimal("500.00"), month=8, year=2025)
        )

        # Regular expense
        await _make_expense(session, acc_id, cat_id, Decimal("100.00"), datetime.date(2025, 8, 1))

        # Internal transfer with EXPENSE type — should be excluded
        await TransactionService(session).create(
            TransactionCreate(
                account_id=acc_id,
                category_id=None,
                amount=Decimal("999.00"),
                type=TransactionType.TRANSFER,
                date=datetime.date(2025, 8, 15),
                is_internal_transfer=True,
            )
        )

        result = await svc.range_summary(datetime.date(2025, 8, 1), datetime.date(2025, 8, 31))
        assert result[0].actual_amount == Decimal("100.00")


# ── list_for_year ───────────────────────────────────────────────────────────────


class TestListForYear:
    async def test_list_for_year_returns_only_that_year(
        self, svc: BudgetService, session: AsyncSession
    ):
        cat_id = await _make_category(session)
        # Budgets in 2024 and 2025
        await svc.create(
            BudgetCreate(category_id=cat_id, amount=Decimal("100.00"), month=6, year=2024)
        )
        await svc.create(
            BudgetCreate(category_id=cat_id, amount=Decimal("200.00"), month=3, year=2025)
        )
        await svc.create(
            BudgetCreate(category_id=cat_id, amount=Decimal("300.00"), month=9, year=2025)
        )

        result = await svc.list_for_year(2025)
        assert len(result) == 2
        assert all(b.year == 2025 for b in result)

    async def test_list_for_year_empty_when_no_budgets(self, svc: BudgetService):
        result = await svc.list_for_year(2099)
        assert result == []

    async def test_list_for_year_ordered_by_month(self, svc: BudgetService, session: AsyncSession):
        cat_id = await _make_category(session)
        await svc.create(
            BudgetCreate(category_id=cat_id, amount=Decimal("100.00"), month=12, year=2025)
        )
        await svc.create(
            BudgetCreate(category_id=cat_id, amount=Decimal("100.00"), month=1, year=2025)
        )
        await svc.create(
            BudgetCreate(category_id=cat_id, amount=Decimal("100.00"), month=6, year=2025)
        )

        result = await svc.list_for_year(2025)
        months = [b.month for b in result]
        assert months == sorted(months)


# ── list filtered by year + month ──────────────────────────────────────────────


class TestListFiltered:
    async def test_list_filtered_by_year_and_month_returns_only_that_month(
        self, svc: BudgetService, session: AsyncSession
    ):
        cat_id = await _make_category(session, name="Utilities")
        await svc.create(
            BudgetCreate(category_id=cat_id, amount=Decimal("100.00"), month=1, year=2025)
        )
        await svc.create(
            BudgetCreate(category_id=cat_id, amount=Decimal("200.00"), month=2, year=2025)
        )
        await svc.create(
            BudgetCreate(category_id=cat_id, amount=Decimal("300.00"), month=1, year=2026)
        )

        result = await svc.list(month=1, year=2025)
        assert len(result) == 1
        assert result[0].month == 1
        assert result[0].year == 2025

    async def test_list_no_filter_returns_all(self, svc: BudgetService, session: AsyncSession):
        cat_id = await _make_category(session, name="Transport")
        await svc.create(
            BudgetCreate(category_id=cat_id, amount=Decimal("50.00"), month=1, year=2025)
        )
        await svc.create(
            BudgetCreate(category_id=cat_id, amount=Decimal("50.00"), month=2, year=2025)
        )

        result = await svc.list()
        assert len(result) == 2

    async def test_list_filtered_empty_when_no_match(self, svc: BudgetService):
        result = await svc.list(month=7, year=2099)
        assert result == []


# ── realization_for_month ─────────────────────────────────────────────────────


class TestRealizationForMonth:
    async def test_empty_month_returns_empty_list(self, svc: BudgetService):
        result = await svc.realization_for_month(2025, 6)
        assert result == []

    async def test_on_track_row_current_month(self, svc: BudgetService, session: AsyncSession):
        cat_id = await _make_category(session, name="Food")
        acc_id = await _make_account(session)
        await svc.create(
            BudgetCreate(category_id=cat_id, amount=Decimal("1000.00"), month=4, year=2026)
        )
        # 15 / 30 = 50% elapsed, spent 300 / 1000 = 30% used → on-track
        await _make_expense(session, acc_id, cat_id, Decimal("300.00"), datetime.date(2026, 4, 10))

        result = await svc.realization_for_month(
            2026, 4, today=datetime.date(2026, 4, 15)
        )
        assert len(result) == 1
        row = result[0]
        assert row.category_name == "Food"
        assert row.planned == Decimal("1000.00")
        assert row.actual == Decimal("300.00")
        assert row.remaining == Decimal("700.00")
        assert row.elapsed_pct == pytest.approx(50.0)
        assert row.used_pct == pytest.approx(30.0)
        assert row.status.value == "on_track"

    async def test_warning_row(self, svc: BudgetService, session: AsyncSession):
        cat_id = await _make_category(session, name="Dining")
        acc_id = await _make_account(session)
        await svc.create(
            BudgetCreate(category_id=cat_id, amount=Decimal("1000.00"), month=4, year=2026)
        )
        # 30% elapsed, used 80% → well over elapsed+5, still under 100 → warning
        await _make_expense(session, acc_id, cat_id, Decimal("800.00"), datetime.date(2026, 4, 5))

        result = await svc.realization_for_month(
            2026, 4, today=datetime.date(2026, 4, 9)
        )
        assert len(result) == 1
        assert result[0].status.value == "warning"

    async def test_over_row(self, svc: BudgetService, session: AsyncSession):
        cat_id = await _make_category(session, name="Shopping")
        acc_id = await _make_account(session)
        await svc.create(
            BudgetCreate(category_id=cat_id, amount=Decimal("500.00"), month=4, year=2026)
        )
        await _make_expense(session, acc_id, cat_id, Decimal("750.00"), datetime.date(2026, 4, 3))

        result = await svc.realization_for_month(
            2026, 4, today=datetime.date(2026, 4, 15)
        )
        assert len(result) == 1
        row = result[0]
        assert row.status.value == "over"
        assert row.used_pct == pytest.approx(150.0)
        assert row.remaining == Decimal("-250.00")

    async def test_past_month_elapsed_is_100(self, svc: BudgetService, session: AsyncSession):
        cat_id = await _make_category(session)
        acc_id = await _make_account(session)
        await svc.create(
            BudgetCreate(category_id=cat_id, amount=Decimal("500.00"), month=2, year=2026)
        )
        await _make_expense(session, acc_id, cat_id, Decimal("400.00"), datetime.date(2026, 2, 10))

        result = await svc.realization_for_month(
            2026, 2, today=datetime.date(2026, 4, 15)
        )
        assert result[0].elapsed_pct == pytest.approx(100.0)
        # used 80% < elapsed 100% + 5 → on_track (finished under budget)
        assert result[0].status.value == "on_track"

    async def test_future_month_elapsed_is_0(self, svc: BudgetService, session: AsyncSession):
        cat_id = await _make_category(session)
        await svc.create(
            BudgetCreate(category_id=cat_id, amount=Decimal("500.00"), month=8, year=2026)
        )

        result = await svc.realization_for_month(
            2026, 8, today=datetime.date(2026, 4, 15)
        )
        assert result[0].elapsed_pct == pytest.approx(0.0)
        assert result[0].used_pct == pytest.approx(0.0)
        assert result[0].status.value == "on_track"

    async def test_rows_sorted_worst_first(self, svc: BudgetService, session: AsyncSession):
        food = await _make_category(session, name="Food")
        dining = await _make_category(session, name="Dining")
        shopping = await _make_category(session, name="Shopping")
        acc_id = await _make_account(session)

        await svc.create(
            BudgetCreate(category_id=food, amount=Decimal("1000.00"), month=4, year=2026)
        )
        await svc.create(
            BudgetCreate(category_id=dining, amount=Decimal("1000.00"), month=4, year=2026)
        )
        await svc.create(
            BudgetCreate(category_id=shopping, amount=Decimal("1000.00"), month=4, year=2026)
        )

        # Food: on-track (300), Dining: warning (800), Shopping: over (1200)
        d = datetime.date(2026, 4, 5)
        await _make_expense(session, acc_id, food, Decimal("300.00"), d)
        await _make_expense(session, acc_id, dining, Decimal("800.00"), d)
        await _make_expense(session, acc_id, shopping, Decimal("1200.00"), d)

        result = await svc.realization_for_month(
            2026, 4, today=datetime.date(2026, 4, 15)
        )
        names = [r.category_name for r in result]
        assert names == ["Shopping", "Dining", "Food"]

    async def test_unbudgeted_spending_appears_with_planned_zero(
        self, svc: BudgetService, session: AsyncSession
    ):
        """Expense in a category with no budget entry still surfaces — used_pct = inf → over."""
        cat_id = await _make_category(session, name="Surprises")
        acc_id = await _make_account(session)
        await _make_expense(session, acc_id, cat_id, Decimal("50.00"), datetime.date(2026, 4, 10))

        result = await svc.realization_for_month(
            2026, 4, today=datetime.date(2026, 4, 15)
        )
        assert len(result) == 1
        assert result[0].planned == Decimal("0")
        assert result[0].actual == Decimal("50.00")
        assert result[0].status.value == "over"

    async def test_parent_name_populated_when_category_has_parent(
        self, svc: BudgetService, session: AsyncSession
    ):
        parent = await CategoryService(session).create(
            CategoryCreate(name="Living", type=CategoryType.EXPENSE)
        )
        child = await CategoryService(session).create(
            CategoryCreate(name="Rent", type=CategoryType.EXPENSE, parent_id=parent.id)
        )
        await svc.create(
            BudgetCreate(category_id=child.id, amount=Decimal("2000.00"), month=4, year=2026)
        )

        result = await svc.realization_for_month(
            2026, 4, today=datetime.date(2026, 4, 15)
        )
        assert len(result) == 1
        assert result[0].category_name == "Rent"
        assert result[0].parent_id == parent.id
        assert result[0].parent_name == "Living"

    async def test_internal_transfers_excluded(self, svc: BudgetService, session: AsyncSession):
        cat_id = await _make_category(session)
        acc_id = await _make_account(session)
        await svc.create(
            BudgetCreate(category_id=cat_id, amount=Decimal("1000.00"), month=4, year=2026)
        )
        await TransactionService(session).create(
            TransactionCreate(
                account_id=acc_id,
                category_id=cat_id,
                amount=Decimal("500.00"),
                type=TransactionType.TRANSFER,
                date=datetime.date(2026, 4, 10),
                is_internal_transfer=True,
            )
        )
        result = await svc.realization_for_month(
            2026, 4, today=datetime.date(2026, 4, 15)
        )
        assert result[0].actual == Decimal("0")
