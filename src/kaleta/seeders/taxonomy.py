# SPDX-License-Identifier: AGPL-3.0-or-later
"""Categories, tags, payees and one categorisation rule.

The vocabulary everything else is filed under, so it seeds first. The
subscriptions tree is built here too: ADR 028 makes the flagged root category
the definition of "what is a subscription charge", and a ledger seeded without
it leaves the Subscriptions panel empty.
"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.categorisation_rule import CategorisationRule, RuleMatchMode
from kaleta.models.category import Category, CategoryType
from kaleta.models.payee import Payee
from kaleta.models.tag import Tag
from kaleta.seeders.base import Seeder, row_count
from kaleta.seeders.catalog import (
    CANONICAL_TAGS,
    CATEGORY_PAYEES,
    EXPENSE_CATEGORIES,
    FALLBACK_PAYEES,
    INCOME_CATEGORIES,
    SUBSCRIPTION_CHILDREN,
    SUBSCRIPTIONS_ROOT,
)


def curated_payee_names() -> list[str]:
    """Every merchant the ledger can name, curated pools first.

    ``Payee.name`` is unique and several categories share a merchant, so the
    curated pools are flattened through a set before the fallbacks are added.
    """
    curated = sorted({name for pool in CATEGORY_PAYEES.values() for name in pool})
    return curated + [name for name in FALLBACK_PAYEES if name not in curated]


class TaxonomySeeder(Seeder):
    key = "taxonomy"
    icon = "sell"

    async def count(self, session: AsyncSession) -> int:
        return await row_count(session, Category)

    async def create(self, session: AsyncSession) -> dict[str, int]:
        expense = [Category(name=name, type=CategoryType.EXPENSE) for name in EXPENSE_CATEGORIES]
        income = [Category(name=name, type=CategoryType.INCOME) for name in INCOME_CATEGORIES]
        # A second "Subskrypcje" beside the flat one: the flat category is what
        # the budgets and the expense loop use, the flagged root is what the
        # Subscriptions panel reads. ADR 028 keeps them distinct on purpose.
        root = Category(
            name=SUBSCRIPTIONS_ROOT,
            type=CategoryType.EXPENSE,
            is_subscriptions_root=True,
        )
        session.add_all([*expense, *income, root])
        await session.flush()

        children = [
            Category(name=name, type=CategoryType.EXPENSE, parent_id=root.id)
            for name in SUBSCRIPTION_CHILDREN
        ]
        tags = [Tag(name=name, icon=icon, color=color) for name, icon, color in CANONICAL_TAGS]
        payees = [Payee(name=name) for name in curated_payee_names()]
        session.add_all([*children, *tags, *payees])
        await session.flush()

        food = next(category for category in expense if category.name == "Żywność")
        rule = CategorisationRule(
            pattern="LIDL",
            match_mode=RuleMatchMode.CONTAINS,
            category_id=food.id,
            is_active=True,
            priority=0,
        )
        session.add(rule)

        return {
            "categories": len(expense) + len(income) + 1 + len(children),
            "tags": len(tags),
            "payees": len(payees),
            "categorisation_rules": 1,
        }

    async def remove(self, session: AsyncSession) -> None:
        await session.execute(delete(CategorisationRule))
        await session.execute(delete(Tag))
        await session.execute(delete(Payee))
        # Children first: the parent FK is SET NULL, but deleting a root while
        # its children still point at it leaves orphans in the tree the
        # Subscriptions panel walks.
        children = (
            (await session.execute(select(Category).where(Category.parent_id.isnot(None))))
            .scalars()
            .all()
        )
        for child in children:
            await session.delete(child)
        await session.flush()
        await session.execute(delete(Category))
