# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for the example-data seeder registry.

The property under test throughout is idempotence: a seeder that finds its own
rows in place must do nothing. That is what makes the Settings buttons safe to
press twice and what lets the CLI be run against a database that is already
half full.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.account import Account
from kaleta.models.asset import Asset
from kaleta.models.budget import Budget
from kaleta.models.category import Category
from kaleta.models.credit import CreditCardProfile
from kaleta.models.institution import Institution
from kaleta.models.payee import Payee
from kaleta.models.personal_loan import PersonalLoan
from kaleta.models.planned_transaction import PlannedTransaction
from kaleta.models.reserve_fund import ReserveFund
from kaleta.models.subscription import Subscription
from kaleta.models.tag import Tag
from kaleta.models.transaction import Transaction
from kaleta.seeders import (
    SEED_FEATURE_KEYS,
    SEEDERS,
    SEEDERS_BY_KEY,
    seed_all,
    seed_features,
    seed_status,
)

#: The table behind each feature, for the "only its own rows" assertions.
_MODEL_FOR = {
    "taxonomy": Category,
    "accounts": Account,
    "assets": Asset,
    "transactions": Transaction,
    "budgets": Budget,
    "planned": PlannedTransaction,
    "subscriptions": Subscription,
    "reserve_funds": ReserveFund,
    "personal_loans": PersonalLoan,
    "credit_cards": CreditCardProfile,
}


async def _count(session: AsyncSession, model: type) -> int:
    return int((await session.execute(select(func.count()).select_from(model))).scalar_one())


class TestRegistryShape:
    def test_every_seeder_is_reachable_by_key(self) -> None:
        assert set(SEEDERS_BY_KEY) == set(SEED_FEATURE_KEYS)
        assert len(SEEDERS) == len(SEED_FEATURE_KEYS)

    def test_keys_are_unique(self) -> None:
        assert len(set(SEED_FEATURE_KEYS)) == len(SEED_FEATURE_KEYS)

    def test_every_feature_has_a_table_in_this_test_module(self) -> None:
        """A new seeder must be added to the assertions below, not slip past them."""
        assert set(_MODEL_FOR) == set(SEED_FEATURE_KEYS)

    def test_dependencies_come_earlier_in_the_registry(self) -> None:
        seen: set[str] = set()
        for seeder in SEEDERS:
            assert set(seeder.depends_on) <= seen, seeder.key
            seen.add(seeder.key)

    def test_every_dependency_names_a_registered_seeder(self) -> None:
        for seeder in SEEDERS:
            for dependency in seeder.depends_on:
                assert dependency in SEEDERS_BY_KEY


@pytest.mark.asyncio
class TestSeedAll:
    async def test_every_table_gets_at_least_one_row(self, session: AsyncSession) -> None:
        await seed_all(session)
        for key, model in _MODEL_FOR.items():
            assert await _count(session, model) > 0, key
        # Tables no single feature is named after, but that the demo needs.
        assert await _count(session, Institution) > 0
        assert await _count(session, Payee) > 0
        assert await _count(session, Tag) > 0

    async def test_a_second_run_writes_nothing(self, session: AsyncSession) -> None:
        await seed_all(session)
        before = {key: await _count(session, model) for key, model in _MODEL_FOR.items()}

        outcomes = await seed_all(session)

        assert all(outcome.skipped for outcome in outcomes)
        assert all(outcome.total == 0 for outcome in outcomes)
        after = {key: await _count(session, model) for key, model in _MODEL_FOR.items()}
        assert after == before

    async def test_replace_rewrites_without_growing(self, session: AsyncSession) -> None:
        await seed_all(session)
        before = {key: await _count(session, model) for key, model in _MODEL_FOR.items()}

        await seed_all(session, replace=True)

        after = {key: await _count(session, model) for key, model in _MODEL_FOR.items()}
        assert after == before

    async def test_status_reports_what_each_feature_holds(self, session: AsyncSession) -> None:
        assert await seed_status(session) == dict.fromkeys(SEED_FEATURE_KEYS, 0)
        await seed_all(session)
        status = await seed_status(session)
        assert set(status) == set(SEED_FEATURE_KEYS)
        assert all(count > 0 for count in status.values())


@pytest.mark.asyncio
class TestSeedOneFeature:
    async def test_accounts_leaves_the_other_tables_alone(self, session: AsyncSession) -> None:
        await seed_features(session, ["accounts"])

        assert await _count(session, Account) > 0
        assert await _count(session, Institution) > 0
        for key in ("taxonomy", "transactions", "budgets", "planned", "subscriptions"):
            assert await _count(session, _MODEL_FOR[key]) == 0, key

    async def test_a_feature_pulls_in_what_it_stands_on(self, session: AsyncSession) -> None:
        outcomes = await seed_features(session, ["transactions"])

        assert [outcome.key for outcome in outcomes] == ["taxonomy", "accounts", "transactions"]
        assert await _count(session, Transaction) > 0
        # …and nothing it does not need.
        assert await _count(session, Budget) == 0
        assert await _count(session, ReserveFund) == 0

    async def test_seeding_the_same_feature_twice_adds_nothing(self, session: AsyncSession) -> None:
        await seed_features(session, ["reserve_funds"])
        before = await _count(session, ReserveFund)

        outcomes = await seed_features(session, ["reserve_funds"])

        assert [outcome.skipped for outcome in outcomes if outcome.key == "reserve_funds"] == [True]
        assert await _count(session, ReserveFund) == before

    async def test_replace_of_one_feature_spares_its_dependencies(
        self, session: AsyncSession
    ) -> None:
        await seed_features(session, ["transactions"])
        accounts_before = {
            account.id: account.name
            for account in (await session.execute(select(Account))).scalars().all()
        }

        await seed_features(session, ["transactions"], replace=True)

        accounts_after = {
            account.id: account.name
            for account in (await session.execute(select(Account))).scalars().all()
        }
        # Replacing the ledger must not renumber the accounts it posts to: the
        # dependency was pulled in, not asked for.
        assert accounts_after == accounts_before

    async def test_an_unknown_key_is_ignored(self, session: AsyncSession) -> None:
        assert await seed_features(session, ["not-a-feature"]) == []


@pytest.mark.asyncio
class TestLedgerShape:
    """The seeded ledger has to satisfy what the BDD scenarios already assert."""

    async def test_transfers_are_linked_in_both_directions(self, session: AsyncSession) -> None:
        await seed_features(session, ["transactions"])
        legs = (
            (await session.execute(select(Transaction).where(Transaction.is_internal_transfer)))
            .scalars()
            .all()
        )
        assert legs
        by_id = {leg.id: leg for leg in legs}
        for leg in legs:
            assert leg.linked_transaction_id in by_id
            assert by_id[leg.linked_transaction_id].linked_transaction_id == leg.id

    async def test_account_balances_match_the_rows_behind_them(self, session: AsyncSession) -> None:
        await seed_features(session, ["transactions"])
        accounts = (await session.execute(select(Account))).scalars().all()
        # Every account the ledger posts to ends up with a balance the rows
        # explain — zero would mean the builder never applied them.
        assert any(account.balance != 0 for account in accounts)
