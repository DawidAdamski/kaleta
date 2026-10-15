# SPDX-License-Identifier: AGPL-3.0-or-later
"""Example data in a family as Alembic builds it.

Migration ``a4e9b2f1c6d8`` plants an English subscriptions tree in every family
schema; the taxonomy seeder must neither take it for the user's data nor add a
second root beside it.

Covers: KAL-PLT-010
"""

from __future__ import annotations

from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.category import Category, CategoryType
from kaleta.models.tag import Tag
from kaleta.seeders import SEED_FEATURE_KEYS, seed_features, seed_status
from kaleta.seeders.catalog import CANONICAL_TAGS


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
    # The seeder adds the Polish purpose children by blind index; the "Monthly"
    # child the test planted stays (it is not touched by the seeder).
    assert sorted(children) == [
        "Chmura i kopie",
        "Inne",
        "Monthly",
        "Muzyka i audio",
        "Oprogramowanie i aplikacje",
        "Prasa i czytanie",
        "Sport i zdrowie",
        "Streaming wideo",
        "Telefon i internet",
    ]


async def test_seeding_a_family_that_already_has_the_canonical_tags(
    session: AsyncSession,
) -> None:
    """Seeding must not die on the canonical tags a fresh family already carries.

    Migration ``b9d4e2c8a1f5`` seeds the eight canonical tags into every family
    schema. The taxonomy seeder used to insert them again unconditionally and
    die on ``uq_tags_name_bidx`` — the "seed everything" failure seen in
    dogfooding on a brand-new family.

    Covers: KAL-PLT-011
    """
    # Stand in for the migration: plant the canonical tags before seeding.
    for name, _icon, _color in CANONICAL_TAGS:
        session.add(Tag(name=name))
    await session.commit()

    [outcome] = await seed_features(session, ["taxonomy"])

    assert not outcome.skipped
    # All eight already existed, so the seeder added none of them — the count
    # reflects rows actually written.
    assert outcome.counts["tags"] == 0
    # Each canonical tag exists exactly once — the pre-existing ones were
    # skipped, not duplicated.
    counts = Counter((await session.execute(select(Tag.name))).scalars().all())
    for name, _icon, _color in CANONICAL_TAGS:
        assert counts[name] == 1, f"{name!r} seeded {counts[name]} times"
