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

from kaleta.models.account import Account, AccountType
from kaleta.models.category import Category, CategoryType
from kaleta.models.transaction import Transaction, TransactionType
from kaleta.seeders.catalog import SUBSCRIPTION_CHILDREN as SUBSCRIPTION_PURPOSE_CHILDREN_PL
from kaleta.services import CategoryService, SubscriptionService
from kaleta.services.category_service import SUBSCRIPTION_PURPOSE_CHILDREN
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
