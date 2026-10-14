# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Subscriptions tree, organised by what you pay for, not how often it bills.

Part A of ``subscriptions-categories``: the seeded children become purpose
groups (Streaming, Music & audio, …); an empty, unreferenced billing-period
child left over from the old tree is retired, but one a family filed charges
under stays. Charges under the tree group by their purpose category.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from kaleta.exceptions import ConflictError
from kaleta.models.account import Account, AccountType
from kaleta.models.category import Category, CategoryType
from kaleta.models.transaction import Transaction, TransactionType
from kaleta.schemas.subscription import SubscriptionCreate
from kaleta.seeders.catalog import SUBSCRIPTION_CHILDREN as SUBSCRIPTION_PURPOSE_CHILDREN_PL
from kaleta.services import CategoryService, SubscriptionService
from kaleta.services.category_service import SUBSCRIPTION_PURPOSE_CHILDREN
from kaleta.services.subscription_service import suggest_purpose_index
from tests.conftest import make_session_factory


async def _seed_root_with_children(session, names: tuple[str, ...]) -> Category:
    """A Subscriptions root with the given direct children."""
    root = Category(name="Subscriptions", type=CategoryType.EXPENSE, is_subscriptions_root=True)
    session.add(root)
    await session.flush()
    for name in names:
        session.add(Category(name=name, type=CategoryType.EXPENSE, parent_id=root.id))
    await session.commit()
    return root


async def _seed_root_with_cadence_children(session) -> Category:
    """Recreate the old English tree: a Subscriptions root with Monthly/Yearly/Other."""
    return await _seed_root_with_children(session, ("Monthly", "Yearly", "Other"))


async def test_subscriptions_tree_is_organised_by_purpose(db_engine) -> None:
    """Covers: KAL-SUB-005

    A family that opens Subscriptions for the first time gets the purpose
    children — Streaming, Music & audio, Software & apps, Phone & internet,
    News & reading, Fitness & health, Cloud & backup, Other — not a split by
    billing period.
    """
    async with make_session_factory(db_engine)() as session:
        svc = CategoryService(session)
        root = await svc.ensure_subscriptions_root_and_children()
        children = await svc.list_subscription_children()

    assert {c.name for c in children} == set(SUBSCRIPTION_PURPOSE_CHILDREN)
    assert all(c.parent_id == root.id for c in children)


async def test_an_empty_billing_period_child_is_retired(db_engine) -> None:
    """Covers: KAL-SUB-006

    The old tree's Monthly/Yearly/Other children hold nothing, so opening the
    page replaces them with the eight purpose children — the cadence ones go.
    """
    async with make_session_factory(db_engine)() as session:
        await _seed_root_with_cadence_children(session)
        svc = CategoryService(session)
        await svc.ensure_subscriptions_root_and_children()
        children = await svc.list_subscription_children()

    assert {c.name for c in children} == set(SUBSCRIPTION_PURPOSE_CHILDREN)


async def test_a_used_billing_period_child_stays(db_engine) -> None:
    """Covers: KAL-SUB-006

    A family that filed a charge under "Monthly" keeps it — it is their data —
    beside the newly added purpose children.
    """
    async with make_session_factory(db_engine)() as session:
        await _seed_root_with_cadence_children(session)
        monthly = next(
            c
            for c in (await CategoryService(session).list_subscription_children())
            if c.name == "Monthly"
        )
        account = Account(name="Konto", type=AccountType.CHECKING, opening_balance=Decimal("0"))
        session.add(account)
        await session.flush()
        session.add(
            Transaction(
                account_id=account.id,
                category_id=monthly.id,
                amount=Decimal("-49.99"),
                type=TransactionType.EXPENSE,
                date=datetime.date(2026, 4, 1),
                description="Netflix",
            )
        )
        await session.commit()

        svc = CategoryService(session)
        await svc.ensure_subscriptions_root_and_children()
        names = {c.name for c in await svc.list_subscription_children()}

    # "Monthly" stays (it holds a charge); "Yearly" is retired (empty); the eight
    # purpose children are added — "Other" was already there as the cadence catch-all.
    assert "Monthly" in names
    assert "Yearly" not in names
    assert names == set(SUBSCRIPTION_PURPOSE_CHILDREN) | {"Monthly"}


async def test_charges_group_under_their_purpose_category(db_engine) -> None:
    """Covers: KAL-SUB-005

    Two Netflix charges filed under "Streaming" show up as one Streaming group
    whose total is their sum.
    """
    async with make_session_factory(db_engine)() as session:
        cats = CategoryService(session)
        await cats.ensure_subscriptions_root_and_children()
        streaming = next(
            c for c in await cats.list_subscription_children() if c.name == "Streaming"
        )
        account = Account(name="Konto", type=AccountType.CHECKING, opening_balance=Decimal("0"))
        session.add(account)
        await session.flush()
        for day in (2, 3):
            session.add(
                Transaction(
                    account_id=account.id,
                    category_id=streaming.id,
                    amount=Decimal("-49.99"),
                    type=TransactionType.EXPENSE,
                    date=datetime.date(2026, 4, day),
                    description="Netflix",
                )
            )
        await session.commit()

        groups = await SubscriptionService(session).subscription_transactions_grouped(
            today=datetime.date(2026, 4, 30)
        )

    streaming_group = next(g for g in groups if g.category_name == "Streaming")
    total = sum(m.total_spent for m in streaming_group.merchants)
    assert total == Decimal("99.98")


async def test_polish_billing_period_children_migrate_to_polish_purpose(db_engine) -> None:
    """Covers: KAL-SUB-006

    A Polish family whose tree still holds Miesięczne / Roczne / Inne, opened with
    Polish names, keeps "Inne" (the catch-all), retires the empty Miesięczne and
    Roczne, and gains the Polish purpose children — no English ones appear.
    """
    async with make_session_factory(db_engine)() as session:
        await _seed_root_with_children(session, ("Miesięczne", "Roczne", "Inne"))
        svc = CategoryService(session)
        await svc.ensure_subscriptions_root_and_children(
            CategoryService.default_purpose_children("pl")
        )
        names = {c.name for c in await svc.list_subscription_children()}

    assert names == set(SUBSCRIPTION_PURPOSE_CHILDREN_PL)
    assert "Inne" in names
    assert "Miesięczne" not in names and "Roczne" not in names
    assert names.isdisjoint(set(SUBSCRIPTION_PURPOSE_CHILDREN) - {"Other"})


async def test_a_polish_purpose_tree_is_not_doubled_with_english(db_engine) -> None:
    """Covers: KAL-SUB-006

    A tree already organised by purpose in Polish (the example seed) is left as it
    is when the page later opens with English defaults — not shown twice.
    """
    async with make_session_factory(db_engine)() as session:
        await _seed_root_with_children(session, SUBSCRIPTION_PURPOSE_CHILDREN_PL)
        svc = CategoryService(session)
        await svc.ensure_subscriptions_root_and_children(list(SUBSCRIPTION_PURPOSE_CHILDREN))
        names = [c.name for c in await svc.list_subscription_children()]

    assert sorted(names) == sorted(SUBSCRIPTION_PURPOSE_CHILDREN_PL)


async def test_ensure_is_idempotent_on_a_second_run(db_engine) -> None:
    """Covers: KAL-SUB-005

    Running ensure twice leaves exactly the eight purpose children — no duplicates.
    """
    async with make_session_factory(db_engine)() as session:
        svc = CategoryService(session)
        await svc.ensure_subscriptions_root_and_children()
        await svc.ensure_subscriptions_root_and_children()
        names = [c.name for c in await svc.list_subscription_children()]

    assert sorted(names) == sorted(SUBSCRIPTION_PURPOSE_CHILDREN)


async def _account(session) -> Account:
    account = Account(name="Konto", type=AccountType.CHECKING, opening_balance=Decimal("0"))
    session.add(account)
    await session.flush()
    return account


async def test_refiling_a_subscription_moves_its_matching_history(db_engine) -> None:
    """Covers: KAL-SUB-007

    Filing a subscription under a purpose child re-files the charges that match
    it (same merchant-key + amount bucket) in the detector window; an unrelated
    charge is left alone, and the subscription itself is filed under the child.
    """
    async with make_session_factory(db_engine)() as session:
        cats = CategoryService(session)
        await cats.ensure_subscriptions_root_and_children()
        streaming = next(
            c for c in await cats.list_subscription_children() if c.name == "Streaming"
        )
        account = await _account(session)
        for day in (2, 3):
            session.add(
                Transaction(
                    account_id=account.id,
                    amount=Decimal("-49.99"),
                    type=TransactionType.EXPENSE,
                    date=datetime.date(2026, 4, day),
                    description="Netflix",
                )
            )
        session.add(
            Transaction(
                account_id=account.id,
                amount=Decimal("-12.00"),
                type=TransactionType.EXPENSE,
                date=datetime.date(2026, 4, 4),
                description="Biedronka",
            )
        )
        await session.commit()

        svc = SubscriptionService(session)
        sub = await svc.create(
            SubscriptionCreate(name="Netflix", amount=Decimal("49.99"), cadence_days=30)
        )
        moved = await svc.refile(sub.id, streaming.id, today=datetime.date(2026, 4, 30))
        assert moved == 2

        rows = (await session.execute(select(Transaction))).scalars().all()
        netflix = [tx for tx in rows if tx.description == "Netflix"]
        biedronka = next(tx for tx in rows if tx.description == "Biedronka")
        assert all(tx.category_id == streaming.id for tx in netflix)
        assert biedronka.category_id is None

        refreshed = await svc.get(sub.id)
        assert refreshed is not None
        assert refreshed.category_id == streaming.id


async def test_count_refilable_is_a_dry_run(db_engine) -> None:
    """Covers: KAL-SUB-007

    The count of charges that would move writes nothing — the charge stays
    uncategorised until the move is confirmed.
    """
    async with make_session_factory(db_engine)() as session:
        cats = CategoryService(session)
        await cats.ensure_subscriptions_root_and_children()
        streaming = next(
            c for c in await cats.list_subscription_children() if c.name == "Streaming"
        )
        account = await _account(session)
        session.add(
            Transaction(
                account_id=account.id,
                amount=Decimal("-49.99"),
                type=TransactionType.EXPENSE,
                date=datetime.date(2026, 4, 2),
                description="Netflix",
            )
        )
        await session.commit()

        svc = SubscriptionService(session)
        sub = await svc.create(SubscriptionCreate(name="Netflix", amount=Decimal("49.99")))
        would_move = await svc.count_refilable(
            sub.id, streaming.id, today=datetime.date(2026, 4, 30)
        )
        assert would_move == 1

        # description is EncryptedText (not filterable in SQL) — load and check in Python.
        rows = (await session.execute(select(Transaction))).scalars().all()
        netflix = [tx for tx in rows if tx.description == "Netflix"]
        assert len(netflix) == 1
        assert netflix[0].category_id is None


async def test_a_known_merchant_suggests_its_purpose_child(db_engine) -> None:
    """Covers: KAL-SUB-008

    A curated merchant (Spotify) resolves to the real "Music & audio" child of
    the seeded tree; an unknown merchant resolves to nothing.
    """
    async with make_session_factory(db_engine)() as session:
        cats = CategoryService(session)
        await cats.ensure_subscriptions_root_and_children()
        children = await cats.list_subscription_children()
        index_map = SubscriptionService.purpose_child_index_map(children)
        music = next(c for c in children if c.name == "Music & audio")

        index = suggest_purpose_index("Spotify P34324")
        assert index is not None
        assert index_map[index] == music.id

        assert suggest_purpose_index("Biedronka 1234") is None


async def test_subscriptions_root_cannot_be_deleted(db_engine) -> None:
    """Covers: KAL-CAT-014

    The flagged Subscriptions root anchors the subscriptions panel and the
    unplanned radar, and deleting it would cascade away its subtree and null
    the linked transactions. ``delete`` must refuse it while still deleting an
    ordinary category.
    """
    async with make_session_factory(db_engine)() as session:
        svc = CategoryService(session)
        root = await svc.ensure_subscriptions_root_and_children()
        normal = Category(name="Groceries", type=CategoryType.EXPENSE)
        session.add(normal)
        await session.flush()
        normal_id = normal.id
        await session.commit()

        with pytest.raises(ConflictError):
            await svc.delete(root.id)

        # The root survives; an ordinary category still deletes.
        assert await svc.get(root.id) is not None
        assert await svc.delete(normal_id) is True
