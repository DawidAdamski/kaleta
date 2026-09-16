# SPDX-License-Identifier: AGPL-3.0-or-later
"""The counts the login panel is allowed to show (artboard 3f).

The panel is read before anyone has proved who they are, so what it may say
is as much the point as whether the numbers are right.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.account import AccountType
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.category import CategoryCreate, CategoryType
from kaleta.schemas.transaction import TransactionCreate, TransactionType
from kaleta.services import AccountService, CategoryService, TransactionService
from kaleta.services.auth_stats_service import (
    AuthLandingStats,
    AuthStatsService,
    months_between,
    reset_auth_stats_cache,
)


@pytest.fixture(autouse=True)
def _no_cache() -> None:
    # The cache is per process and a minute long; a test that read another
    # test's numbers would pass for the wrong reason.
    reset_auth_stats_cache()


class TestMonthsBetween:
    def test_one_day_of_history_is_one_month(self) -> None:
        # Not zero: there is something in the ledger, and "0 months" beside a
        # transaction count would contradict itself.
        day = datetime.date(2026, 3, 14)
        assert months_between(day, day) == 1

    def test_both_ends_are_counted(self) -> None:
        assert months_between(datetime.date(2026, 1, 31), datetime.date(2026, 3, 1)) == 3

    def test_a_span_across_new_year(self) -> None:
        assert months_between(datetime.date(2025, 11, 2), datetime.date(2026, 2, 20)) == 4

    def test_an_empty_ledger_has_no_ends_and_so_no_months(self) -> None:
        assert months_between(None, None) == 0
        assert months_between(datetime.date(2026, 1, 1), None) == 0
        assert months_between(None, datetime.date(2026, 1, 1)) == 0


@pytest.mark.asyncio
class TestLandingStats:
    async def test_an_empty_database_still_answers(self, session: AsyncSession) -> None:
        stats = await AuthStatsService(session).landing_stats()
        assert stats == AuthLandingStats(transactions=0, accounts=0, months=0)

    async def test_the_three_counts(self, session: AsyncSession) -> None:
        accounts = AccountService(session)
        first = await accounts.create(
            AccountCreate(name="Checking", type=AccountType.CHECKING, balance=Decimal("0"))
        )
        await accounts.create(
            AccountCreate(name="Savings", type=AccountType.SAVINGS, balance=Decimal("0"))
        )
        category = await CategoryService(session).create(
            CategoryCreate(name="Food", type=CategoryType.EXPENSE)
        )
        transactions = TransactionService(session)
        for day in (datetime.date(2026, 1, 10), datetime.date(2026, 3, 2)):
            await transactions.create(
                TransactionCreate(
                    account_id=first.id,
                    category_id=category.id,
                    amount=Decimal("10.00"),
                    type=TransactionType.EXPENSE,
                    date=day,
                    description="x",
                )
            )

        stats = await AuthStatsService(session).landing_stats()
        assert stats == AuthLandingStats(transactions=2, accounts=2, months=3)

    async def test_it_counts_and_says_nothing_else(self, session: AsyncSession) -> None:
        # The panel is pre-login. Three integers is the whole contract: no
        # names, no amounts, nothing that describes what the ledger says.
        assert {f for f in AuthLandingStats.__dataclass_fields__} == {
            "transactions",
            "accounts",
            "months",
        }
        stats = AuthLandingStats(transactions=1, accounts=1, months=1)
        assert all(
            isinstance(getattr(stats, f), int) for f in AuthLandingStats.__dataclass_fields__
        )
