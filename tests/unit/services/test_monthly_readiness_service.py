"""Unit tests for MonthlyReadinessService + BudgetService.copy_forward."""

from __future__ import annotations

import datetime
import json
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.account import AccountType
from kaleta.models.category import CategoryType
from kaleta.models.planned_transaction import RecurrenceFrequency
from kaleta.models.transaction import Transaction, TransactionType
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.budget import BudgetCreate
from kaleta.schemas.category import CategoryCreate
from kaleta.schemas.planned_transaction import PlannedTransactionCreate
from kaleta.schemas.transaction import TransactionCreate
from kaleta.services import (
    AccountService,
    BudgetService,
    CategoryService,
    MonthlyReadinessService,
    PlannedTransactionService,
    TransactionService,
)


async def _seed_account(session: AsyncSession) -> int:
    a = await AccountService(session).create(
        AccountCreate(name="Checking", type=AccountType.CHECKING)
    )
    return a.id


async def _seed_category(
    session: AsyncSession, name: str, cat_type: CategoryType = CategoryType.EXPENSE
) -> int:
    c = await CategoryService(session).create(CategoryCreate(name=name, type=cat_type))
    return c.id


# ── BudgetService.copy_forward ───────────────────────────────────────────────


class TestCopyForward:
    async def test_copies_missing_months(self, session: AsyncSession):
        cat = await _seed_category(session, "Food")
        bsvc = BudgetService(session)
        await bsvc.create(
            BudgetCreate(category_id=cat, amount=Decimal("500"), month=1, year=2026)
        )
        written = await bsvc.copy_forward(2026, 1, 2026, 2)
        assert written == 1
        rows = await bsvc.list_for_month(2026, 2)
        assert len(rows) == 1
        assert rows[0].amount == Decimal("500")

    async def test_skips_existing_without_overwrite(self, session: AsyncSession):
        cat = await _seed_category(session, "Food")
        bsvc = BudgetService(session)
        await bsvc.create(
            BudgetCreate(category_id=cat, amount=Decimal("500"), month=1, year=2026)
        )
        await bsvc.create(
            BudgetCreate(category_id=cat, amount=Decimal("999"), month=2, year=2026)
        )
        written = await bsvc.copy_forward(2026, 1, 2026, 2)
        assert written == 0
        rows = await bsvc.list_for_month(2026, 2)
        assert rows[0].amount == Decimal("999")  # unchanged

    async def test_overwrite_replaces_existing(self, session: AsyncSession):
        cat = await _seed_category(session, "Food")
        bsvc = BudgetService(session)
        await bsvc.create(
            BudgetCreate(category_id=cat, amount=Decimal("500"), month=1, year=2026)
        )
        await bsvc.create(
            BudgetCreate(category_id=cat, amount=Decimal("999"), month=2, year=2026)
        )
        written = await bsvc.copy_forward(2026, 1, 2026, 2, overwrite=True)
        assert written == 1
        rows = await bsvc.list_for_month(2026, 2)
        assert rows[0].amount == Decimal("500")

    async def test_empty_source_returns_zero(self, session: AsyncSession):
        assert await BudgetService(session).copy_forward(2026, 1, 2026, 2) == 0

    async def test_december_to_january_crosses_year(self, session: AsyncSession):
        cat = await _seed_category(session, "Food")
        bsvc = BudgetService(session)
        await bsvc.create(
            BudgetCreate(category_id=cat, amount=Decimal("123"), month=12, year=2025)
        )
        written = await bsvc.copy_forward(2025, 12, 2026, 1)
        assert written == 1
        rows = await bsvc.list_for_month(2026, 1)
        assert rows[0].amount == Decimal("123")


# ── MonthlyReadinessService — persistence ───────────────────────────────────


class TestMarkStage:
    async def test_get_or_create_returns_row_with_defaults(self, session: AsyncSession):
        svc = MonthlyReadinessService(session)
        row = await svc.get_or_create(2026, 4)
        assert row.id is not None
        assert row.stage_1_done is False
        assert row.stage_4_done is False
        assert row.ready_at is None

    async def test_get_or_create_is_idempotent(self, session: AsyncSession):
        svc = MonthlyReadinessService(session)
        a = await svc.get_or_create(2026, 4)
        b = await svc.get_or_create(2026, 4)
        assert a.id == b.id

    async def test_mark_stage_toggles(self, session: AsyncSession):
        svc = MonthlyReadinessService(session)
        row = await svc.mark_stage(2026, 4, 1)
        assert row.stage_1_done is True
        row = await svc.mark_stage(2026, 4, 1, done=False)
        assert row.stage_1_done is False

    async def test_all_four_stamps_ready_at(self, session: AsyncSession):
        svc = MonthlyReadinessService(session)
        for s in (1, 2, 3, 4):
            row = await svc.mark_stage(2026, 4, s)
        assert row.ready_at is not None

    async def test_undoing_a_stage_clears_ready_at(self, session: AsyncSession):
        svc = MonthlyReadinessService(session)
        for s in (1, 2, 3, 4):
            await svc.mark_stage(2026, 4, s)
        row = await svc.mark_stage(2026, 4, 2, done=False)
        assert row.ready_at is None

    async def test_set_seen_persists(self, session: AsyncSession):
        svc = MonthlyReadinessService(session)
        ids = await svc.set_seen(2026, 4, planned_id=42, seen=True)
        assert ids == [42]
        ids = await svc.set_seen(2026, 4, planned_id=42, seen=False)
        assert ids == []


# ── Stage evaluators ─────────────────────────────────────────────────────────


class TestStage1:
    async def test_counts_uncategorised_last_month_only(self, session: AsyncSession):
        acc = await _seed_account(session)
        cat = await _seed_category(session, "Food")
        tx_svc = TransactionService(session)
        # 2 uncategorised last month (March 2026) — insert via model to bypass
        # the schema validator that requires a category for expense rows.
        for d in (datetime.date(2026, 3, 5), datetime.date(2026, 3, 15)):
            session.add(
                Transaction(
                    amount=Decimal("10"),
                    type=TransactionType.EXPENSE,
                    account_id=acc,
                    category_id=None,
                    date=d,
                    description="x",
                )
            )
        await session.commit()
        # 1 categorised last month — should not count
        await tx_svc.create(
            TransactionCreate(
                amount=Decimal("10"),
                type=TransactionType.EXPENSE,
                account_id=acc,
                category_id=cat,
                date=datetime.date(2026, 3, 20),
                description="y",
            )
        )
        # 1 uncategorised this month — should not count
        session.add(
            Transaction(
                amount=Decimal("10"),
                type=TransactionType.EXPENSE,
                account_id=acc,
                category_id=None,
                date=datetime.date(2026, 4, 1),
                description="z",
            )
        )
        await session.commit()
        svc = MonthlyReadinessService(session)
        s1 = await svc.stage_1(2026, 4)
        assert s1.last_year == 2026
        assert s1.last_month == 3
        assert s1.uncategorised_count == 2

    async def test_january_rolls_to_december_previous_year(
        self, session: AsyncSession
    ):
        svc = MonthlyReadinessService(session)
        s1 = await svc.stage_1(2026, 1)
        assert s1.last_year == 2025
        assert s1.last_month == 12


class TestStage2:
    async def test_no_recurring_income_returns_empty(self, session: AsyncSession):
        svc = MonthlyReadinessService(session)
        s2 = await svc.stage_2(2026, 4)
        assert s2.rows == []

    async def test_recurring_income_compared_against_actuals(
        self, session: AsyncSession
    ):
        acc = await _seed_account(session)
        cat_income = await _seed_category(session, "Salary", CategoryType.INCOME)
        await PlannedTransactionService(session).create(
            PlannedTransactionCreate(
                name="Salary",
                amount=Decimal("5000"),
                type=TransactionType.INCOME,
                account_id=acc,
                category_id=cat_income,
                frequency=RecurrenceFrequency.MONTHLY,
                interval=1,
                start_date=datetime.date(2026, 4, 1),
                is_active=True,
            )
        )
        # Actual income landed
        await TransactionService(session).create(
            TransactionCreate(
                amount=Decimal("5000"),
                type=TransactionType.INCOME,
                account_id=acc,
                category_id=cat_income,
                date=datetime.date(2026, 4, 2),
                description="payroll",
            )
        )
        svc = MonthlyReadinessService(session)
        s2 = await svc.stage_2(2026, 4)
        assert len(s2.rows) == 1
        assert s2.rows[0].expected == Decimal("5000")
        assert s2.rows[0].actual == Decimal("5000.00")


class TestStage3:
    async def test_preview_flags_new_vs_existing(self, session: AsyncSession):
        cat_a = await _seed_category(session, "A")
        cat_b = await _seed_category(session, "B")
        bsvc = BudgetService(session)
        # Source month: both A and B
        await bsvc.create(
            BudgetCreate(category_id=cat_a, amount=Decimal("100"), month=3, year=2026)
        )
        await bsvc.create(
            BudgetCreate(category_id=cat_b, amount=Decimal("200"), month=3, year=2026)
        )
        # Target month: only A already present
        await bsvc.create(
            BudgetCreate(category_id=cat_a, amount=Decimal("999"), month=4, year=2026)
        )
        svc = MonthlyReadinessService(session)
        s3 = await svc.stage_3(2026, 4)
        assert s3.from_year == 2026 and s3.from_month == 3
        assert s3.to_year == 2026 and s3.to_month == 4
        assert s3.new_count == 1
        assert s3.skipped_count == 1

    async def test_apply_writes_only_new_rows(self, session: AsyncSession):
        cat_a = await _seed_category(session, "A")
        cat_b = await _seed_category(session, "B")
        bsvc = BudgetService(session)
        await bsvc.create(
            BudgetCreate(category_id=cat_a, amount=Decimal("100"), month=3, year=2026)
        )
        await bsvc.create(
            BudgetCreate(category_id=cat_b, amount=Decimal("200"), month=3, year=2026)
        )
        await bsvc.create(
            BudgetCreate(category_id=cat_a, amount=Decimal("999"), month=4, year=2026)
        )
        svc = MonthlyReadinessService(session)
        written = await svc.apply_stage_3(2026, 4)
        assert written == 1
        rows = await bsvc.list_for_month(2026, 4)
        by_cat = {r.category_id: r.amount for r in rows}
        assert by_cat[cat_a] == Decimal("999")  # preserved
        assert by_cat[cat_b] == Decimal("200")  # copied


class TestStage4:
    async def test_lists_planned_expenses_with_seen_state(self, session: AsyncSession):
        acc = await _seed_account(session)
        cat = await _seed_category(session, "Rent")
        pt = await PlannedTransactionService(session).create(
            PlannedTransactionCreate(
                name="Rent",
                amount=Decimal("2000"),
                type=TransactionType.EXPENSE,
                account_id=acc,
                category_id=cat,
                frequency=RecurrenceFrequency.MONTHLY,
                interval=1,
                start_date=datetime.date(2026, 4, 1),
                is_active=True,
            )
        )
        svc = MonthlyReadinessService(session)
        s4 = await svc.stage_4(2026, 4)
        assert len(s4.rows) == 1
        assert s4.rows[0].planned_id == pt.id
        assert s4.rows[0].seen is False
        assert s4.rows[0].amount == Decimal("2000.00")
        # Mark seen and re-evaluate
        await svc.set_seen(2026, 4, pt.id, seen=True)
        s4b = await svc.stage_4(2026, 4)
        assert s4b.rows[0].seen is True
        assert s4b.all_seen is True

    async def test_excludes_income_planned_transactions(self, session: AsyncSession):
        acc = await _seed_account(session)
        cat = await _seed_category(session, "Salary", CategoryType.INCOME)
        await PlannedTransactionService(session).create(
            PlannedTransactionCreate(
                name="Salary",
                amount=Decimal("5000"),
                type=TransactionType.INCOME,
                account_id=acc,
                category_id=cat,
                frequency=RecurrenceFrequency.MONTHLY,
                interval=1,
                start_date=datetime.date(2026, 4, 1),
                is_active=True,
            )
        )
        s4 = await MonthlyReadinessService(session).stage_4(2026, 4)
        assert s4.rows == []


class TestSeenPersistence:
    async def test_seen_json_starts_empty(self, session: AsyncSession):
        svc = MonthlyReadinessService(session)
        row = await svc.get_or_create(2026, 4)
        assert json.loads(row.seen_planned_ids) == []
