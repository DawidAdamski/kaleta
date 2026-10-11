# SPDX-License-Identifier: AGPL-3.0-or-later
"""The re-key budget: a 50 000-transaction ledger re-keys in under 60 seconds.

``hosted-household-sharing`` §3. The measurement on the CI PostgreSQL goes into
the plan's Implementation notes; a slower run here is a regression in the
re-key, not a reason to raise the number.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, insert, select

from kaleta.db import AsyncSessionFactory
from kaleta.db.tenant_context import use_tenant
from kaleta.db.types import use_data_key
from kaleta.models.account import Account
from kaleta.models.transaction import Transaction, TransactionType
from kaleta.services.household_service import HouseholdService
from tests.household_helpers import (
    PARTNER,
    act,
    approved_partner,
    household_database,
    member_id_of,
    owner_with_data,
)

pytestmark = pytest.mark.slow

ROWS = 50_000
BUDGET_SECONDS = 60.0


@pytest.fixture
async def household_db() -> AsyncIterator[str]:
    async with household_database() as url:
        yield url


async def test_a_50k_row_ledger_rekeys_within_budget(household_db: str) -> None:
    owner = await owner_with_data(household_db)
    await approved_partner(household_db, owner)
    key = owner.unlocked_key()
    assert key is not None
    start_day = date(2020, 1, 1)
    with use_tenant(owner.context(key)), use_data_key(key):
        async with AsyncSessionFactory() as session:
            account = Account(name="Konto wspólne")
            session.add(account)
            await session.flush()
            rows = [
                {
                    "account_id": account.id,
                    "amount": Decimal("-12.34"),
                    "type": TransactionType.EXPENSE,
                    "date": start_day + timedelta(days=n % 2000),
                    "description": f"Zakupy spożywcze #{n}",
                    "notes": "paragon w szufladzie" if n % 3 == 0 else None,
                }
                for n in range(ROWS)
            ]
            for chunk in range(0, ROWS, 5000):
                await session.execute(insert(Transaction), rows[chunk : chunk + 5000])
            await session.commit()

    member_id = await member_id_of(owner, PARTNER)

    async def _remove(service: HouseholdService) -> None:
        await service.remove(member_id, key)

    started = time.perf_counter()
    await act(owner, _remove)
    elapsed = time.perf_counter() - started
    print(f"\nre-key of {ROWS} transactions: {elapsed:.1f} s")

    new = owner.unlocked_key()
    assert new is not None and new.version == 2
    with use_tenant(owner.context(new)), use_data_key(new):
        async with AsyncSessionFactory() as session:
            assert await session.scalar(select(func.count()).select_from(Transaction)) == ROWS
            stale = await session.scalar(
                select(func.count())
                .select_from(Transaction)
                .where(func.get_byte(Transaction.__table__.c.description, 1) != 2)
            )
            assert stale == 0
            last = await session.scalar(
                select(Transaction.description).order_by(Transaction.id.desc()).limit(1)
            )
            assert last == f"Zakupy spożywcze #{ROWS - 1}"
    assert elapsed < BUDGET_SECONDS
