# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration coverage for the planned transactions in scripts/seed.py.

Covers: KAL-PLT-005
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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import kaleta.models  # noqa: F401 — register ORM tables on Base.metadata
from kaleta.models.planned_transaction import PlannedTransaction
from kaleta.models.transaction import TransactionType
from kaleta.services.planned_transaction_service import PlannedTransactionService

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SEED_SCRIPT = PROJECT_ROOT / "scripts" / "seed.py"

# Literals from KAL-PLT-005.
MIN_PLANNED = 12
CALENDAR_WINDOW_DAYS = 60
MIN_DISTINCT_DAYS = 9
EXPECTED_INTERVAL = 1


@pytest.fixture(scope="module")
def seeded_db_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    """Run scripts/seed.py once against a throwaway SQLite file."""
    tmp_path = tmp_path_factory.mktemp("seed_calendar")
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


def test_seed_fills_the_payment_calendar(seeded_session: AsyncSession) -> None:
    """Covers: KAL-PLT-005"""

    async def _check() -> None:
        planned = (await seeded_session.execute(select(PlannedTransaction))).scalars().all()
        assert len(planned) >= MIN_PLANNED
        assert all(p.is_active for p in planned)
        assert all(p.interval == EXPECTED_INTERVAL for p in planned)

        today = datetime.date.today()
        occurrences = await PlannedTransactionService(seeded_session).get_occurrences(
            today, today + datetime.timedelta(days=CALENDAR_WINDOW_DAYS)
        )
        assert len({o.date for o in occurrences}) >= MIN_DISTINCT_DAYS

        salary = [o for o in occurrences if o.type == TransactionType.INCOME]
        assert salary, "no planned income occurrence in the calendar window"

    asyncio.run(_check())
