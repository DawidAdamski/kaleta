# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration coverage for the payee and tag fan-out in scripts/seed.py.

Covers: KAL-PLT-003, KAL-PLT-004
"""

from __future__ import annotations

import asyncio
import datetime
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

import kaleta.models  # noqa: F401 — register ORM tables on Base.metadata
from kaleta.models.payee import Payee
from kaleta.models.transaction import Transaction, TransactionType
from kaleta.services.report_service import ReportService

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SEED_SCRIPT = PROJECT_ROOT / "scripts" / "seed.py"

# Literals from KAL-PLT-003.
MIN_PAYEES = 25
MIN_TRANSACTIONS_PER_PAYEE = 3


@pytest.fixture(scope="module")
def seeded_db_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    """Run scripts/seed.py once against a throwaway SQLite file."""
    tmp_path = tmp_path_factory.mktemp("seed")
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'seed.db'}"
    home = tmp_path / "home"
    home.mkdir()
    proc = subprocess.run(
        [sys.executable, str(SEED_SCRIPT)],
        cwd=PROJECT_ROOT,
        env={**os.environ, "HOME": str(home), "KALETA_DB_URL": db_url},
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    return db_url


@pytest.fixture
def seeded_session(seeded_db_url: str) -> Iterator[AsyncSession]:
    """An open session on the seeded database, closed after the test."""
    engine = create_async_engine(seeded_db_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        asyncio.run(session.close())
        asyncio.run(engine.dispose())


def test_seed_attaches_payees_to_transactions(seeded_session: AsyncSession) -> None:
    """Covers: KAL-PLT-003"""

    async def _check() -> None:
        counts = (
            await seeded_session.execute(
                select(Payee.name, func.count(Transaction.id))
                .join(Transaction, Transaction.payee_id == Payee.id)
                .group_by(Payee.name)
            )
        ).all()

        assert len(counts) >= MIN_PAYEES
        thin = [name for name, cnt in counts if cnt < MIN_TRANSACTIONS_PER_PAYEE]
        assert thin == [], (
            f"payees with fewer than {MIN_TRANSACTIONS_PER_PAYEE} transactions: {thin}"
        )

        today = datetime.date.today()
        merchants = await ReportService(seeded_session).top_merchants(
            start=today - datetime.timedelta(days=365),
            end=today + datetime.timedelta(days=1),
        )
        assert merchants != []

    asyncio.run(_check())


def test_seed_tags_expenses_transfers_and_subscriptions(seeded_session: AsyncSession) -> None:
    """Covers: KAL-PLT-004"""

    async def _check() -> None:
        rows = (
            (
                await seeded_session.execute(
                    select(Transaction).options(
                        selectinload(Transaction.tags),
                        selectinload(Transaction.category),
                    )
                )
            )
            .scalars()
            .all()
        )
        assert rows

        def names(tx: Transaction) -> set[str]:
            return {tag.name for tag in tx.tags}

        expenses = [tx for tx in rows if tx.type == TransactionType.EXPENSE]
        assert expenses
        untagged = [tx.id for tx in expenses if not names(tx) & {"Card", "Cash"}]
        assert untagged == [], f"expenses without a Card/Cash tag: {untagged[:5]}"

        transfers = [tx for tx in rows if tx.type == TransactionType.TRANSFER]
        assert transfers
        assert all("Transfer" in names(tx) for tx in transfers)

        subscriptions = [
            tx for tx in expenses if tx.category is not None and tx.category.name == "Subskrypcje"
        ]
        assert subscriptions
        assert all({"Subscription", "Recurring"} <= names(tx) for tx in subscriptions)

        income = [tx for tx in rows if tx.type == TransactionType.INCOME]
        assert income
        assert all(names(tx) == set() for tx in income)

    asyncio.run(_check())
