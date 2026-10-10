# SPDX-License-Identifier: AGPL-3.0-or-later
"""Example data in a family as Alembic builds it.

Migration ``a4e9b2f1c6d8`` plants an English subscriptions tree in every family
schema; the taxonomy seeder must neither take it for the user's data nor add a
second root beside it.

Covers: KAL-PLT-010
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.category import Category, CategoryType
from kaleta.seeders import SEED_FEATURE_KEYS, seed_features, seed_status


async def test_a_new_familys_subscriptions_tree_is_not_example_data(
    session: AsyncSession,
) -> None:
    """Covers: KAL-PLT-010"""
    root = Category(name="Subscriptions", type=CategoryType.EXPENSE, is_subscriptions_root=True)
    session.add(root)
    await session.flush()
    session.add(Category(name="Monthly", type=CategoryType.EXPENSE, parent_id=root.id))
    await session.commit()
    assert await seed_status(session) == dict.fromkeys(SEED_FEATURE_KEYS, 0)

    [outcome] = await seed_features(session, ["taxonomy"])

    assert not outcome.skipped
    roots = (
        (await session.execute(select(Category).where(Category.is_subscriptions_root.is_(True))))
        .scalars()
        .all()
    )
    assert [r.id for r in roots] == [root.id]
    children = (
        await session.execute(select(Category.name).where(Category.parent_id == root.id))
    ).scalars()
    assert sorted(children) == ["Inne", "Miesięczne", "Monthly", "Roczne"]
