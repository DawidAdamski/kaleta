# SPDX-License-Identifier: AGPL-3.0-or-later
"""Concurrency idempotency of applying a brand-new yearly plan.

Applying a yearly plan (``YearlyPlanService.apply``) writes the single
``yearly_plans`` row for the year and then one ``Budget`` row per
``(category, month, year)``. Both writes used a select-then-insert-or-update
shape, so two overlapping applies of a brand-new plan raced twice: first on
``uq_yearly_plans_year`` (both read no plan row and both INSERT it), then — had
they got past it — on ``uq_budget_category_period`` for the budget rows. Either
surfaced as ``UniqueViolationError``. PR #344 removed the only UI trigger (a
double Confirm from stacked handlers), but the services still raced whenever two
applies overlapped. Both upserts are now one atomic
``INSERT … ON CONFLICT DO UPDATE`` statement each.

A true overlap is driven with two independent engines (independent Postgres
connections) and ``asyncio.gather``, aligned on a barrier so both issue their
read against the empty state before either commits — the exact interleaving that
triggered the bug pre-fix and that the atomic statements tolerate post-fix. (See
``RACERS`` / ``_race`` for why the barrier is needed.)

Covers: KAL-BBD-002
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from decimal import Decimal

import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from kaleta.models.budget import Budget
from kaleta.models.category import Category
from kaleta.models.yearly_plan import YearlyPlan
from kaleta.schemas.budget import BudgetCreate
from kaleta.schemas.category import CategoryCreate, CategoryType
from kaleta.schemas.yearly_plan import VariableLine, YearlyPlanPayload
from kaleta.services.budget_service import BudgetService
from kaleta.services.category_service import CategoryService
from kaleta.services.yearly_plan_service import YearlyPlanService
from tests.conftest import _POSTGRES_URL, SUITE_FAMILY

# Literals from KAL-BBD-002: a brand-new year, one expense category, a uniform
# monthly budget of 100.00 across all twelve months. The apply path derives that
# from a yearly variable line of 1200.00 (1200.00 / 12 = 100.00).
YEAR = 2031
MONTHLY_AMOUNT = Decimal("100.00")
YEARLY_AMOUNT = Decimal("1200.00")
MONTHS = range(1, 13)

# Two applies fired at once, aligned on a barrier (``_race`` below). A single-row
# ``yearly_plans`` INSERT + COMMIT is fast enough that, left to chance under
# single-thread asyncio, the first racer commits before the second even reads —
# so the race never shows. The barrier releases both only once both connections
# are established and both have reached the call, so both issue their read against
# the empty table before either commits: the exact overlap a second web worker
# would create, and the one the fix must tolerate. Post-fix both racers still
# succeed — READ COMMITTED serialises the ON CONFLICT writes through the row lock,
# with no serialization failure to retry.
RACERS = 2

RacingSetup = tuple[int, list[async_sessionmaker], list[object]]


async def _race(
    factories: list[async_sessionmaker],
    work: Callable[[AsyncSession], Awaitable[int]],
) -> list[int]:
    """Run ``work`` on every factory at once, each on its own connection.

    A barrier holds every racer until all of them have an open connection and
    have reached the starting line, maximising the read-before-commit overlap.
    """
    barrier = asyncio.Barrier(len(factories))

    async def _one(factory: async_sessionmaker) -> int:
        async with factory() as session:
            await session.connection()  # establish the connection before the line
            await barrier.wait()
            return await work(session)

    return list(await asyncio.gather(*(_one(f) for f in factories)))


def _independent_factory() -> tuple[async_sessionmaker, object]:
    """A session factory on its own engine — a real, separate Postgres connection.

    Unlike the shared ``db_engine`` fixture (one rolled-back connection), these
    commit for real so several of them can genuinely race. Statements carry the
    family schema through ``schema_translate_map``, exactly as the app's do.
    """
    engine = create_async_engine(
        _POSTGRES_URL,
        poolclass=NullPool,
        execution_options={"schema_translate_map": {None: SUITE_FAMILY.schema}},
    )
    return async_sessionmaker(engine, expire_on_commit=False), engine


async def _purge(factory: async_sessionmaker, category_id: int | None) -> None:
    """Remove every row this test may have committed for ``YEAR``."""
    async with factory() as s:
        await s.execute(delete(Budget).where(Budget.year == YEAR))
        if category_id is not None:
            await s.execute(delete(Budget).where(Budget.category_id == category_id))
        await s.execute(delete(YearlyPlan).where(YearlyPlan.year == YEAR))
        await s.commit()
    if category_id is not None:
        async with factory() as s:
            cat = await s.get(Category, category_id)
            if cat is not None:
                await s.delete(cat)
                await s.commit()


@pytest_asyncio.fixture
async def racing_budget_setup() -> AsyncIterator[RacingSetup]:
    """A committed expense category plus ``RACERS`` independent session factories.

    Cleans up every budget / plan row and the category it created, on both sides
    of the test, so the real commits leave the shared schema as they found it.
    """
    pairs = [_independent_factory() for _ in range(RACERS)]
    factories = [f for f, _ in pairs]
    engines = [e for _, e in pairs]
    category_id: int | None = None
    try:
        await _purge(factories[0], None)
        async with factories[0]() as s:
            category = await CategoryService(s).create(
                CategoryCreate(name="Concurrency Groceries", type=CategoryType.EXPENSE)
            )
            await s.commit()
            category_id = category.id
        yield category_id, factories, engines
    finally:
        await _purge(factories[0], category_id)
        for engine in engines:
            await engine.dispose()


class TestBulkUpsertConcurrency:
    async def test_overlapping_bulk_upserts_write_each_row_once(
        self,
        racing_budget_setup: RacingSetup,
    ) -> None:
        """Covers: KAL-BBD-002

        Concurrent ``bulk_upsert`` calls for the same brand-new budget rows must
        neither raise ``UniqueViolationError`` nor leave duplicate rows.
        """
        category_id, factories, _engines = racing_budget_setup
        entries = [
            BudgetCreate(category_id=category_id, amount=MONTHLY_AMOUNT, month=month, year=YEAR)
            for month in MONTHS
        ]

        async def _work(session: AsyncSession) -> int:
            return await BudgetService(session).bulk_upsert(list(entries))

        # No UniqueViolationError: gather surfaces any racer's exception.
        written = await _race(factories, _work)
        assert all(count == 12 for count in written)

        async with factories[0]() as s:
            rows = await BudgetService(s).list_for_year(YEAR)
        plan_rows = [b for b in rows if b.category_id == category_id]
        assert len(plan_rows) == 12
        assert {b.month for b in plan_rows} == set(MONTHS)
        assert all(b.amount == MONTHLY_AMOUNT for b in plan_rows)

    async def test_overlapping_applies_write_plan_and_rows_once(
        self,
        racing_budget_setup: RacingSetup,
    ) -> None:
        """Covers: KAL-BBD-002

        Concurrent ``YearlyPlanService.apply`` calls for a brand-new year — the
        real Budget Builder path — must neither raise ``UniqueViolationError`` (on
        ``yearly_plans`` or on the budget rows) nor leave duplicates: exactly one
        ``yearly_plans`` row and one budget row per month at 100.00.
        """
        category_id, factories, _engines = racing_budget_setup
        payload = YearlyPlanPayload(
            year=YEAR,
            variable_lines=[
                VariableLine(name="Groceries", amount=YEARLY_AMOUNT, category_id=category_id)
            ],
        )

        async def _work(session: AsyncSession) -> int:
            return await YearlyPlanService(session).apply(payload)

        # No UniqueViolationError on yearly_plans or on the budget rows.
        await _race(factories, _work)

        async with factories[0]() as s:
            plan_result = await s.execute(select(YearlyPlan).where(YearlyPlan.year == YEAR))
            plan_rows = plan_result.scalars().all()
            budgets = await BudgetService(s).list_for_year(YEAR)
        assert len(plan_rows) == 1
        rows = [b for b in budgets if b.category_id == category_id]
        assert len(rows) == 12
        assert {b.month for b in rows} == set(MONTHS)
        assert all(b.amount == MONTHLY_AMOUNT for b in rows)
