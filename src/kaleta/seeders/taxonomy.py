# SPDX-License-Identifier: AGPL-3.0-or-later
"""Categories, tags, payees and one categorisation rule.

The vocabulary everything else is filed under, so it seeds first. The
subscriptions tree is built here too: ADR 028 makes the flagged root category
the definition of "what is a subscription charge", and a ledger seeded without
it leaves the Subscriptions panel empty.

Every family schema is built by Alembic, and migration ``a4e9b2f1c6d8`` plants
an English subscriptions tree in it. That tree is not the user's data: it does
not count as "already seeded", and the seeder files its children under that
root rather than adding a second one.
"""

from __future__ import annotations

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.db.types import exact_index
from kaleta.models.categorisation_rule import CategorisationRule, RuleMatchMode
from kaleta.models.category import Category, CategoryType
from kaleta.models.payee import Payee
from kaleta.models.payee_identity import PayeeIdentity
from kaleta.models.payee_merge import DismissedPayeeMerge, PayeeAutoMerge
from kaleta.models.tag import Tag
from kaleta.seeders.base import Seeder
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
        """Categories outside the subscriptions tree a new family starts with."""
        roots = select(Category.id).where(Category.is_subscriptions_root.is_(True))
        result = await session.execute(
            select(func.count())
            .select_from(Category)
            .where(
                Category.is_subscriptions_root.is_(False),
                or_(Category.parent_id.is_(None), Category.parent_id.not_in(roots)),
            )
        )
        return int(result.scalar_one())

    async def create(self, session: AsyncSession) -> dict[str, int]:
        expense = [Category(name=name, type=CategoryType.EXPENSE) for name in EXPENSE_CATEGORIES]
        income = [Category(name=name, type=CategoryType.INCOME) for name in INCOME_CATEGORIES]
        # A second "Subskrypcje" beside the flat one: the flat category is what
        # the budgets and the expense loop use, the flagged root is what the
        # Subscriptions panel reads. ADR 028 keeps them distinct on purpose.
        root = (
            await session.execute(select(Category).where(Category.is_subscriptions_root.is_(True)))
        ).scalar_one_or_none()
        planted = root is None
        if root is None:
            root = Category(
                name=SUBSCRIPTIONS_ROOT,
                type=CategoryType.EXPENSE,
                is_subscriptions_root=True,
            )
        session.add_all([*expense, *income, root])
        await session.flush()

        filed = set(
            (
                await session.execute(
                    select(Category.name_bidx).where(Category.parent_id == root.id)
                )
            ).scalars()
        )
        children = [
            Category(name=name, type=CategoryType.EXPENSE, parent_id=root.id)
            for name in SUBSCRIPTION_CHILDREN
            if exact_index(name) not in filed
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
            "categories": len(expense) + len(income) + int(planted) + len(children),
            "tags": len(tags),
            "payees": len(payees),
            "categorisation_rules": 1,
        }

    async def remove(self, session: AsyncSession) -> None:
        await session.execute(delete(CategorisationRule))
        await session.execute(delete(Tag))
        # Bulk deletes skip the ORM cascade: clear what hangs off payees
        # before the payees themselves.
        for dependant in (PayeeAutoMerge, DismissedPayeeMerge, PayeeIdentity):
            await session.execute(delete(dependant))
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
