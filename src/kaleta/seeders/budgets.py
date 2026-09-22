# SPDX-License-Identifier: AGPL-3.0-or-later
"""A monthly budget for every month the ledger covers.

Amounts scale with inflation the same way the transactions do, so a
budget-versus-actual chart over six years does not show the plan drifting away
from reality for a reason that is only arithmetic.
"""

from __future__ import annotations

import datetime

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.budget import Budget
from kaleta.seeders.base import Seeder, inflation, month_offset, row_count, zloty
from kaleta.seeders.catalog import BASE_BUDGETS, BUDGETED_CATEGORIES, MONTHS
from kaleta.seeders.lookups import categories_by_name


class BudgetsSeeder(Seeder):
    key = "budgets"
    depends_on = ("taxonomy",)
    icon = "savings"

    async def count(self, session: AsyncSession) -> int:
        return await row_count(session, Budget)

    async def create(self, session: AsyncSession) -> dict[str, int]:
        categories = await categories_by_name(session)
        today = datetime.date.today()
        rows: list[Budget] = []
        for months_back in range(MONTHS):
            year, month = month_offset(today, months_back)
            factor = inflation(months_back)
            for name in BUDGETED_CATEGORIES:
                rows.append(
                    Budget(
                        category_id=categories[name].id,
                        amount=zloty(float(BASE_BUDGETS[name]) * factor),
                        month=month,
                        year=year,
                    )
                )
        session.add_all(rows)
        return {"budgets": len(rows)}

    async def remove(self, session: AsyncSession) -> None:
        await session.execute(delete(Budget))
