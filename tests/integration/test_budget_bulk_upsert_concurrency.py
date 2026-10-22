# SPDX-License-Identifier: AGPL-3.0-or-later
"""Concurrency idempotency of ``BudgetService.bulk_upsert`` for a brand-new plan.

Two overlapping applies of the same brand-new ``(category, month, year)`` set
must not race on ``uq_budget_category_period``: the former select-then-insert
shape let both transactions read no existing row and both INSERT it, so the
second hit the unique constraint (``UniqueViolationError``). The fix makes the
upsert one atomic ``INSERT … ON CONFLICT DO UPDATE`` statement.

This exercises ``bulk_upsert`` directly — the layer the fix lives in — rather
than ``YearlyPlanService.apply``. ``apply`` also writes the single ``yearly_plans``
row for the year, which has its own ``uq_yearly_plans_year`` uniqueness that two
concurrent applies would race on independently; that is a separate concern,
out of this slice's scope, so the test isolates the budget-row race.

A true overlap is driven with two independent engines (independent Postgres
connections) and ``asyncio.gather``: each ``bulk_upsert`` issues its read as its
first await, so both transactions read the empty state before either commits —
the exact interleaving that triggers the bug pre-fix and that the atomic
statement tolerates post-fix.

Covers: KAL-BBD-002
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from decimal import Decimal

import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from kaleta.models.budget import Budget
from kaleta.models.category import Category
from kaleta.schemas.budget import BudgetCreate
from kaleta.schemas.category import CategoryCreate, CategoryType
from kaleta.services.budget_service import BudgetService
from kaleta.services.category_service import CategoryService
from tests.conftest import _POSTGRES_URL, SUITE_FAMILY

# Literals from KAL-BBD-002: a brand-new year, one expense category, a uniform
# monthly budget of 100.00 across all twelve months.
YEAR = 2031
MONTHLY_AMOUNT = Decimal("100.00")
MONTHS = range(1, 13)


def _independent_factory() -> tuple[async_sessionmaker, object]:
    """A session factory on its own engine — a real, separate Postgres connection.

    Unlike the shared ``db_engine`` fixture (one rolled-back connection), these
    commit for real so two of them can genuinely race. Statements carry the
    family schema through ``schema_translate_map``, exactly as the app's do.
    """
    engine = create_async_engine(
        _POSTGRES_URL,
        poolclass=NullPool,
        execution_options={"schema_translate_map": {None: SUITE_FAMILY.schema}},
    )
    return async_sessionmaker(engine, expire_on_commit=False), engine


RacingSetup = tuple[int, async_sessionmaker, async_sessionmaker]


@pytest_asyncio.fixture
async def racing_budget_setup() -> AsyncIterator[RacingSetup]:
    """A committed expense category plus two independent session factories.

    Cleans up every budget row and the category it created, on both sides of
    the test, so the real commits leave the shared schema as they found it.
    """
    factory_a, engine_a = _independent_factory()
    factory_b, engine_b = _independent_factory()

    async def _purge() -> None:
        async with factory_a() as s:
            await s.execute(delete(Budget).where(Budget.year == YEAR))
            await s.commit()

    try:
        await _purge()
        async with factory_a() as s:
            category = await CategoryService(s).create(
                CategoryCreate(name="Concurrency Groceries", type=CategoryType.EXPENSE)
            )
            await s.commit()
            category_id = category.id
        yield category_id, factory_a, factory_b
    finally:
        async with factory_a() as s:
            await s.execute(delete(Budget).where(Budget.year == YEAR))
            await s.execute(delete(Budget).where(Budget.category_id == category_id))
            await s.commit()
        async with factory_a() as s:
            cat = await s.get(Category, category_id)
            if cat is not None:
                await s.delete(cat)
                await s.commit()
        await engine_a.dispose()
        await engine_b.dispose()


class TestBulkUpsertConcurrency:
    async def test_two_overlapping_applies_write_each_row_once(
        self,
        racing_budget_setup: RacingSetup,
    ) -> None:
        """Covers: KAL-BBD-002

        Two concurrent ``bulk_upsert`` calls for the same brand-new plan must
        neither raise ``UniqueViolationError`` nor leave duplicate rows.
        """
        category_id, factory_a, factory_b = racing_budget_setup
        entries = [
            BudgetCreate(category_id=category_id, amount=MONTHLY_AMOUNT, month=month, year=YEAR)
            for month in MONTHS
        ]

        async def _apply(factory: async_sessionmaker) -> int:
            async with factory() as s:
                return await BudgetService(s).bulk_upsert(list(entries))

        # No UniqueViolationError: gather surfaces either side's exception.
        written_a, written_b = await asyncio.gather(_apply(factory_a), _apply(factory_b))
        assert written_a == 12
        assert written_b == 12

        # Exactly one row per month, each at the planned amount.
        async with factory_a() as s:
            rows = await BudgetService(s).list_for_year(YEAR)
        plan_rows = [b for b in rows if b.category_id == category_id]
        assert len(plan_rows) == 12
        assert {b.month for b in plan_rows} == set(MONTHS)
        assert all(b.amount == MONTHLY_AMOUNT for b in plan_rows)
