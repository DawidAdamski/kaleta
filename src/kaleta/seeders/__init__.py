# SPDX-License-Identifier: AGPL-3.0-or-later
"""Example data, one feature at a time.

The registry below is the only entry point. It holds the seeders in dependency
order, so "Seed everything" is a walk down the list and seeding one feature is
that feature plus whatever it stands on — a transaction cannot exist without an
account, and a user who presses *Transactions* on an empty database means "give
me transactions", not "fail".

Idempotence is the property that matters: every function here can be called
again on a database it already filled and will report what it skipped rather
than doubling it. That is what makes the Settings buttons safe and what lets
``scripts/seed.py`` be a thin wrapper over the same code the UI runs.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.seeders.accounts import AccountsSeeder
from kaleta.seeders.assets import AssetsSeeder
from kaleta.seeders.base import Seeder, SeedOutcome
from kaleta.seeders.budgets import BudgetsSeeder
from kaleta.seeders.credit_cards import CreditCardsSeeder
from kaleta.seeders.personal_loans import PersonalLoansSeeder
from kaleta.seeders.planned import PlannedTransactionsSeeder
from kaleta.seeders.reserve_funds import ReserveFundsSeeder
from kaleta.seeders.subscriptions import SubscriptionsSeeder
from kaleta.seeders.taxonomy import TaxonomySeeder
from kaleta.seeders.transactions import TransactionsSeeder

__all__ = [
    "SEEDERS",
    "SEEDERS_BY_KEY",
    "SEED_FEATURE_KEYS",
    "SeedOutcome",
    "Seeder",
    "seed_all",
    "seed_features",
    "seed_status",
]

#: Dependency order — a seeder never appears before something it needs.
SEEDERS: tuple[Seeder, ...] = (
    TaxonomySeeder(),
    AccountsSeeder(),
    AssetsSeeder(),
    TransactionsSeeder(),
    BudgetsSeeder(),
    PlannedTransactionsSeeder(),
    SubscriptionsSeeder(),
    ReserveFundsSeeder(),
    PersonalLoansSeeder(),
    CreditCardsSeeder(),
)

SEEDERS_BY_KEY: dict[str, Seeder] = {seeder.key: seeder for seeder in SEEDERS}
SEED_FEATURE_KEYS: tuple[str, ...] = tuple(seeder.key for seeder in SEEDERS)


def _with_dependencies(keys: set[str]) -> list[str]:
    """``keys`` plus everything they stand on, back in registry order."""
    wanted: set[str] = set()

    def walk(key: str) -> None:
        if key in wanted:
            return
        seeder = SEEDERS_BY_KEY.get(key)
        if seeder is None:
            return
        wanted.add(key)
        for dependency in seeder.depends_on:
            walk(dependency)

    for key in keys:
        walk(key)
    return [seeder.key for seeder in SEEDERS if seeder.key in wanted]


def _with_dependents(keys: set[str]) -> set[str]:
    """``keys`` plus everything that stands on them, transitively.

    The other direction from :func:`_with_dependencies`, and the one that makes
    ``replace`` safe: a transaction's account and category are plain foreign
    keys with no ``ON DELETE`` rule, so deleting the accounts under a live
    ledger is an integrity error rather than a fresh start.
    """
    wanted = {key for key in keys if key in SEEDERS_BY_KEY}
    changed = True
    while changed:
        changed = False
        for seeder in SEEDERS:
            if seeder.key in wanted:
                continue
            if set(seeder.depends_on) & wanted:
                wanted.add(seeder.key)
                changed = True
    return wanted


async def seed_features(
    session: AsyncSession,
    keys: list[str],
    *,
    replace: bool = False,
) -> list[SeedOutcome]:
    """Seed the named features and their dependencies, oldest layer first.

    Without ``replace`` a feature that already holds example data is left
    exactly as it is, so the call is safe to repeat.

    ``replace`` rewrites the named features **and everything standing on
    them**: the rows are removed in reverse dependency order first — the only
    order the foreign keys allow — and written again in registry order. What
    the named features merely *stand on* is spared; replacing the accounts
    because someone asked to replace the credit-card terms would delete a
    ledger nobody mentioned.
    """
    asked = {key for key in keys if key in SEEDERS_BY_KEY}
    if replace and asked:
        doomed = _with_dependents(asked)
        for seeder in reversed(SEEDERS):
            if seeder.key in doomed:
                await seeder.remove(session)
        await session.flush()
        wanted = _with_dependencies(doomed)
    else:
        wanted = _with_dependencies(asked)

    outcomes: list[SeedOutcome] = []
    for key in wanted:
        outcomes.append(await SEEDERS_BY_KEY[key].seed(session))
    await session.commit()
    return outcomes


async def seed_all(session: AsyncSession, *, replace: bool = False) -> list[SeedOutcome]:
    """Every feature, in dependency order."""
    return await seed_features(session, list(SEED_FEATURE_KEYS), replace=replace)


async def seed_status(session: AsyncSession) -> dict[str, int]:
    """How many rows each feature already owns, so a button can say so."""
    return {seeder.key: await seeder.count(session) for seeder in SEEDERS}
