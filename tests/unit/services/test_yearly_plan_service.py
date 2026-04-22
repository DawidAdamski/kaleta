"""Unit tests for YearlyPlanService — uses in-memory SQLite."""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.account import AccountType
from kaleta.models.category import CategoryType
from kaleta.models.transaction import TransactionType
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.budget import BudgetCreate
from kaleta.schemas.category import CategoryCreate
from kaleta.schemas.transaction import TransactionCreate
from kaleta.schemas.yearly_plan import (
    FixedLine,
    IncomeLine,
    VariableLine,
    YearlyPlanPayload,
)
from kaleta.services import (
    AccountService,
    BudgetService,
    CategoryService,
    TransactionService,
    YearlyPlanService,
)
from kaleta.services.yearly_plan_service import _split_yearly_to_months


async def _make_category(
    session: AsyncSession, name: str, cat_type: CategoryType = CategoryType.EXPENSE
) -> int:
    c = await CategoryService(session).create(CategoryCreate(name=name, type=cat_type))
    return c.id


async def _make_account(session: AsyncSession) -> int:
    a = await AccountService(session).create(AccountCreate(name="Checking", type=AccountType.CHECKING))
    return a.id


# ── _split_yearly_to_months ───────────────────────────────────────────────────


class TestSplitYearlyToMonths:
    def test_zero_yields_zeros(self):
        assert _split_yearly_to_months(Decimal("0")) == [Decimal("0.00")] * 12

    def test_exact_division_is_uniform(self):
        # 1200 / 12 = 100.00 exactly
        assert _split_yearly_to_months(Decimal("1200.00")) == [Decimal("100.00")] * 12

    def test_remainder_spreads_to_last_3(self):
        # 100 / 12 = 8.3333... → base 8.33, remainder 0.04 → last 3 get +0.01, +0.01, +0.02 (order)
        months = _split_yearly_to_months(Decimal("100.00"))
        assert sum(months) == Decimal("100.00")
        # First 9 are base
        assert all(m == months[0] for m in months[:9])
        # Last three are at least base (remainder is positive)
        assert months[9] >= months[0]
        assert months[10] >= months[0]
        assert months[11] >= months[0]

    def test_sum_always_equals_yearly(self):
        for amount in [
            Decimal("1.00"),
            Decimal("7.77"),
            Decimal("99.99"),
            Decimal("1234.56"),
            Decimal("50000.00"),
        ]:
            assert sum(_split_yearly_to_months(amount)) == amount

    def test_negative_not_supported_returns_zeros(self):
        # Guarded: negative yearly → zeros (current behaviour)
        assert _split_yearly_to_months(Decimal("-100.00")) == [Decimal("0.00")] * 12


# ── derive ────────────────────────────────────────────────────────────────────


class TestDerive:
    async def test_empty_payload_returns_empty(self, session: AsyncSession):
        svc = YearlyPlanService(session)
        out = svc.derive(YearlyPlanPayload(year=2026))
        assert out == {}

    async def test_variable_line_produces_12_months(self, session: AsyncSession):
        cat = await _make_category(session, "Food")
        svc = YearlyPlanService(session)
        payload = YearlyPlanPayload(
            year=2026,
            variable_lines=[VariableLine(name="Food", amount=Decimal("1200"), category_id=cat)],
        )
        out = svc.derive(payload)
        assert len(out) == 12
        assert all(out[(cat, m)] == Decimal("100.00") for m in range(1, 13))

    async def test_fixed_with_category_contributes(self, session: AsyncSession):
        cat = await _make_category(session, "Rent")
        svc = YearlyPlanService(session)
        payload = YearlyPlanPayload(
            year=2026,
            fixed_lines=[FixedLine(name="Rent", amount=Decimal("24000"), category_id=cat)],
        )
        out = svc.derive(payload)
        assert out[(cat, 6)] == Decimal("2000.00")

    async def test_fixed_without_category_is_ignored(self, session: AsyncSession):
        svc = YearlyPlanService(session)
        payload = YearlyPlanPayload(
            year=2026,
            fixed_lines=[FixedLine(name="Misc", amount=Decimal("120"), category_id=None)],
        )
        assert svc.derive(payload) == {}

    async def test_multiple_lines_same_category_sum(self, session: AsyncSession):
        cat = await _make_category(session, "Groceries")
        svc = YearlyPlanService(session)
        payload = YearlyPlanPayload(
            year=2026,
            variable_lines=[
                VariableLine(name="Weekday", amount=Decimal("600"), category_id=cat),
                VariableLine(name="Weekend", amount=Decimal("600"), category_id=cat),
            ],
        )
        out = svc.derive(payload)
        assert out[(cat, 1)] == Decimal("100.00")

    async def test_income_lines_do_not_create_budget(self, session: AsyncSession):
        svc = YearlyPlanService(session)
        payload = YearlyPlanPayload(
            year=2026,
            income_lines=[IncomeLine(name="Salary", amount=Decimal("120000"))],
        )
        assert svc.derive(payload) == {}


# ── upsert / get_payload ──────────────────────────────────────────────────────


class TestUpsertAndGet:
    async def test_get_payload_empty_when_no_row(self, session: AsyncSession):
        svc = YearlyPlanService(session)
        payload = await svc.get_payload(2030)
        assert payload.year == 2030
        assert payload.variable_lines == []

    async def test_round_trip(self, session: AsyncSession):
        cat = await _make_category(session, "Food")
        svc = YearlyPlanService(session)
        payload = YearlyPlanPayload(
            year=2026,
            income_lines=[IncomeLine(name="Salary", amount=Decimal("120000.00"))],
            variable_lines=[
                VariableLine(name="Food", amount=Decimal("1200.50"), category_id=cat)
            ],
        )
        await svc.upsert(payload)
        roundtrip = await svc.get_payload(2026)
        assert len(roundtrip.income_lines) == 1
        assert roundtrip.income_lines[0].amount == Decimal("120000.00")
        assert roundtrip.variable_lines[0].amount == Decimal("1200.50")
        assert roundtrip.variable_lines[0].category_id == cat

    async def test_upsert_replaces_existing(self, session: AsyncSession):
        cat = await _make_category(session, "Food")
        svc = YearlyPlanService(session)
        await svc.upsert(
            YearlyPlanPayload(
                year=2026,
                variable_lines=[
                    VariableLine(name="Food", amount=Decimal("1200"), category_id=cat)
                ],
            )
        )
        await svc.upsert(
            YearlyPlanPayload(
                year=2026,
                variable_lines=[
                    VariableLine(name="Food", amount=Decimal("2400"), category_id=cat)
                ],
            )
        )
        rt = await svc.get_payload(2026)
        assert rt.variable_lines[0].amount == Decimal("2400")


# ── apply ─────────────────────────────────────────────────────────────────────


class TestApply:
    async def test_apply_writes_12_budget_rows(self, session: AsyncSession):
        cat = await _make_category(session, "Food")
        svc = YearlyPlanService(session)
        payload = YearlyPlanPayload(
            year=2026,
            variable_lines=[
                VariableLine(name="Food", amount=Decimal("1200"), category_id=cat)
            ],
        )
        written = await svc.apply(payload)
        assert written == 12
        rows = await BudgetService(session).list_for_year(2026)
        assert len(rows) == 12
        assert all(r.amount == Decimal("100.00") for r in rows)

    async def test_apply_idempotent_updates_in_place(self, session: AsyncSession):
        cat = await _make_category(session, "Food")
        svc = YearlyPlanService(session)
        payload = YearlyPlanPayload(
            year=2026,
            variable_lines=[
                VariableLine(name="Food", amount=Decimal("1200"), category_id=cat)
            ],
        )
        await svc.apply(payload)
        # Raise envelope and re-apply
        payload.variable_lines[0].amount = Decimal("2400")
        await svc.apply(payload)
        rows = await BudgetService(session).list_for_year(2026)
        # Still 12 rows (updated, not duplicated)
        assert len(rows) == 12
        assert all(r.amount == Decimal("200.00") for r in rows)

    async def test_apply_sum_matches_yearly_target(self, session: AsyncSession):
        cat = await _make_category(session, "Food")
        svc = YearlyPlanService(session)
        # 1234.56 doesn't divide cleanly — remainder must be spread
        await svc.apply(
            YearlyPlanPayload(
                year=2026,
                variable_lines=[
                    VariableLine(name="Food", amount=Decimal("1234.56"), category_id=cat)
                ],
            )
        )
        rows = await BudgetService(session).list_for_year(2026)
        total = sum((r.amount for r in rows), Decimal("0"))
        assert total == Decimal("1234.56")

    async def test_apply_empty_payload_returns_zero(self, session: AsyncSession):
        svc = YearlyPlanService(session)
        n = await svc.apply(YearlyPlanPayload(year=2026))
        assert n == 0


# ── diff ──────────────────────────────────────────────────────────────────────


class TestDiff:
    async def test_all_added_when_no_current_rows(self, session: AsyncSession):
        cat = await _make_category(session, "Food")
        svc = YearlyPlanService(session)
        diff = await svc.diff(
            YearlyPlanPayload(
                year=2026,
                variable_lines=[
                    VariableLine(name="Food", amount=Decimal("1200"), category_id=cat)
                ],
            )
        )
        assert len(diff.added) == 12
        assert diff.updated == []
        assert diff.unchanged_count == 0

    async def test_unchanged_when_derivation_matches_current(self, session: AsyncSession):
        cat = await _make_category(session, "Food")
        bsvc = BudgetService(session)
        # Pre-populate Budget rows that match a 1200/yr variable line exactly.
        for m in range(1, 13):
            await bsvc.create(
                BudgetCreate(
                    category_id=cat, amount=Decimal("100.00"), month=m, year=2026
                )
            )

        svc = YearlyPlanService(session)
        diff = await svc.diff(
            YearlyPlanPayload(
                year=2026,
                variable_lines=[
                    VariableLine(name="Food", amount=Decimal("1200"), category_id=cat)
                ],
            )
        )
        assert diff.added == []
        assert diff.updated == []
        assert diff.unchanged_count == 12

    async def test_updated_when_amounts_differ(self, session: AsyncSession):
        cat = await _make_category(session, "Food")
        bsvc = BudgetService(session)
        await bsvc.create(
            BudgetCreate(category_id=cat, amount=Decimal("50.00"), month=6, year=2026)
        )

        svc = YearlyPlanService(session)
        diff = await svc.diff(
            YearlyPlanPayload(
                year=2026,
                variable_lines=[
                    VariableLine(name="Food", amount=Decimal("1200"), category_id=cat)
                ],
            )
        )
        # 11 months new + 1 updated (month 6: 50 → 100)
        assert len(diff.added) == 11
        assert len(diff.updated) == 1
        assert diff.updated[0].month == 6
        assert diff.updated[0].current == Decimal("50.00")
        assert diff.updated[0].proposed == Decimal("100.00")


# ── bulk_upsert ────────────────────────────────────────────────────────────────


class TestBulkUpsert:
    async def test_writes_all_entries_and_sums_duplicates(self, session: AsyncSession):
        cat = await _make_category(session, "Food")
        entries = [
            BudgetCreate(category_id=cat, amount=Decimal("100"), month=1, year=2026),
            BudgetCreate(category_id=cat, amount=Decimal("50"), month=1, year=2026),  # duplicate key
            BudgetCreate(category_id=cat, amount=Decimal("200"), month=2, year=2026),
        ]
        written = await BudgetService(session).bulk_upsert(entries)
        # 2 unique keys after merge
        assert written == 2
        rows = await BudgetService(session).list_for_year(2026)
        by_month = {r.month: r.amount for r in rows}
        assert by_month[1] == Decimal("150")
        assert by_month[2] == Decimal("200")

    async def test_empty_list_returns_zero(self, session: AsyncSession):
        assert await BudgetService(session).bulk_upsert([]) == 0
