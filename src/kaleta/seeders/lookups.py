# SPDX-License-Identifier: AGPL-3.0-or-later
"""Finding the rows an earlier seeder wrote.

A seeder never holds a reference to another seeder's objects — the two may run
in separate sessions, or a year apart, and the button for one may be pressed
without the other. They agree on names instead, and those names live in
:mod:`kaleta.seeders.catalog`.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import NotFoundError
from kaleta.models.account import Account, AccountType
from kaleta.models.category import Category, CategoryType
from kaleta.models.payee import Payee
from kaleta.models.tag import Tag
from kaleta.seeders.catalog import ACCOUNT_NAMES

__all__ = [
    "MissingSeedDependencyError",
    "accounts_by_kind",
    "categories_by_name",
    "payees_by_name",
    "subscription_category_ids",
    "tags_by_name",
]


class MissingSeedDependencyError(NotFoundError):
    """A seeder was run without the rows it builds on.

    Only reachable by calling a seeder directly: the registry seeds
    ``depends_on`` first, so the UI and the CLI never see this.
    """


async def categories_by_name(session: AsyncSession) -> dict[str, Category]:
    """Top-level categories, keyed by name.

    Children are left out on purpose: two trees can both hold a "Miesięczne",
    and the ones the seeders name by hand are all at the root.
    """
    rows = (await session.execute(select(Category).where(Category.parent_id.is_(None)))).scalars()
    return {category.name: category for category in rows}


async def subscription_category_ids(session: AsyncSession) -> set[int]:
    """The flagged subscriptions root, its children, and the flat category.

    Both EXPENSE categories named "Subskrypcje" count as subscription spend:
    the flat one the budgets use and the tree the Subscriptions panel reads.
    """
    roots = (
        (await session.execute(select(Category).where(Category.is_subscriptions_root.is_(True))))
        .scalars()
        .all()
    )
    ids = {root.id for root in roots}
    if roots:
        children = (
            (
                await session.execute(
                    select(Category).where(Category.parent_id.in_([root.id for root in roots]))
                )
            )
            .scalars()
            .all()
        )
        ids.update(child.id for child in children)
    flat = (
        await session.execute(
            select(Category).where(
                Category.name == "Subskrypcje",
                Category.type == CategoryType.EXPENSE,
                Category.parent_id.is_(None),
            )
        )
    ).scalars()
    ids.update(category.id for category in flat)
    return ids


async def subscription_child(session: AsyncSession, name: str) -> Category:
    """One child of the subscriptions root, by name."""
    root = (
        await session.execute(select(Category).where(Category.is_subscriptions_root.is_(True)))
    ).scalar_one_or_none()
    if root is None:
        raise MissingSeedDependencyError("the subscriptions root category is missing")
    child = (
        await session.execute(
            select(Category).where(Category.parent_id == root.id, Category.name == name)
        )
    ).scalar_one_or_none()
    if child is None:
        raise MissingSeedDependencyError(f"subscription category {name!r} is missing")
    return child


async def tags_by_name(session: AsyncSession) -> dict[str, Tag]:
    rows = (await session.execute(select(Tag))).scalars()
    return {tag.name: tag for tag in rows}


async def payees_by_name(session: AsyncSession) -> dict[str, Payee]:
    rows = (await session.execute(select(Payee))).scalars()
    return {payee.name: payee for payee in rows}


async def accounts_by_kind(session: AsyncSession) -> dict[str, Account]:
    """The four demo accounts, keyed ``checking`` / ``savings`` / ``cash`` / ``credit``.

    Looked up by name and then by type, so an install where the user renamed
    an account still resolves rather than seeding a second ledger beside it.
    """
    rows = (await session.execute(select(Account))).scalars().all()
    by_name = {account.name: account for account in rows}
    by_type: dict[AccountType, Account] = {}
    for account in rows:
        by_type.setdefault(account.type, account)

    resolved: dict[str, Account] = {}
    for kind, name in ACCOUNT_NAMES.items():
        found = by_name.get(name) or by_type.get(AccountType(kind))
        if found is None:
            raise MissingSeedDependencyError(f"no {kind} account to attach example data to")
        resolved[kind] = found
    return resolved
