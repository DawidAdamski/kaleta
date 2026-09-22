# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration coverage for the per-feature example data.

Covers: KAL-PLT-006, KAL-PLT-007, KAL-PLT-008, KAL-PLT-009, KAL-SET-029
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import kaleta.models  # noqa: F401 — register ORM tables on Base.metadata
from kaleta.config import settings
from kaleta.db.base import Base
from kaleta.debug_info import MASK, build_sections, sections_as_markdown
from kaleta.models.account import Account
from kaleta.models.asset import Asset
from kaleta.models.budget import Budget
from kaleta.models.category import Category
from kaleta.models.credit import CreditCardProfile
from kaleta.models.institution import Institution
from kaleta.models.payee import Payee
from kaleta.models.personal_loan import Counterparty, PersonalLoan, PersonalLoanRepayment
from kaleta.models.planned_transaction import PlannedTransaction
from kaleta.models.reserve_fund import ReserveFund
from kaleta.models.subscription import Subscription
from kaleta.models.tag import Tag
from kaleta.models.transaction import Transaction
from kaleta.seeders import SEED_FEATURE_KEYS, seed_all, seed_features

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SEED_SCRIPT = PROJECT_ROOT / "scripts" / "seed.py"

#: Every table the example data occupies. Compared table by table, so a seeder
#: that quietly stops writing one of them fails rather than averages out.
SEEDED_TABLES = (
    Account,
    Asset,
    Budget,
    Category,
    Counterparty,
    CreditCardProfile,
    Institution,
    Payee,
    PersonalLoan,
    PersonalLoanRepayment,
    PlannedTransaction,
    ReserveFund,
    Subscription,
    Tag,
    Transaction,
)


async def _counts(session: AsyncSession) -> dict[str, int]:
    counts: dict[str, int] = {}
    for model in SEEDED_TABLES:
        result = await session.execute(select(func.count()).select_from(model))
        counts[model.__tablename__] = int(result.scalar_one())
    return counts


def _engine_with_foreign_keys(db_url: str):  # noqa: ANN202 — AsyncEngine
    """An engine that enforces foreign keys, the way the running app does.

    ``tests/conftest.py`` builds its engines without the PRAGMA listener from
    ``kaleta.db.session``, so an ordering bug that SQLite would refuse in
    production passes there unnoticed. Everything in this module goes through
    here instead, which is what makes the ``--replace`` tests mean something.
    """
    engine = create_async_engine(db_url)

    @event.listens_for(engine.sync_engine, "connect")
    def _set_pragma(dbapi_connection, _record):  # noqa: ANN001, ANN202
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


@asynccontextmanager
async def _open_session(db_url: str) -> AsyncIterator[AsyncSession]:
    """A session on ``db_url``, with the engine disposed on the way out.

    Leaving the engine behind leaves aiosqlite's worker thread attached to a
    loop ``asyncio.run`` is about to close, which surfaces as an unrelated
    "Event loop is closed" warning in whatever test runs next.
    """
    engine = _engine_with_foreign_keys(db_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        await session.close()
        await engine.dispose()


@pytest.fixture
def file_db(tmp_path: Path) -> Iterator[str]:
    """An on-disk SQLite database with the schema created from the models."""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'registry.db'}"

    async def _create() -> None:
        engine = _engine_with_foreign_keys(db_url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(_create())
    yield db_url


def _run_seed_cli(tmp_path: Path, db_url: str, *args: str) -> subprocess.CompletedProcess[str]:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return subprocess.run(
        [sys.executable, str(SEED_SCRIPT), *args],
        cwd=PROJECT_ROOT,
        env={**os.environ, "HOME": str(home), "KALETA_DB_URL": db_url},
        check=False,
        capture_output=True,
        text=True,
    )


def test_seed_everything_fills_every_feature_once(file_db: str) -> None:
    """Covers: KAL-PLT-006"""

    async def _check() -> None:
        async with _open_session(file_db) as session:
            outcomes = await seed_all(session)
            assert [outcome.key for outcome in outcomes] == list(SEED_FEATURE_KEYS)
            first = await _counts(session)
            assert all(count > 0 for count in first.values()), first

            again = await seed_all(session)
            assert all(outcome.skipped for outcome in again)
            assert await _counts(session) == first

    asyncio.run(_check())


def test_seeding_accounts_leaves_the_other_tables_empty(file_db: str) -> None:
    """Covers: KAL-PLT-007"""

    async def _check() -> None:
        async with _open_session(file_db) as session:
            await seed_features(session, ["accounts"])
            counts = await _counts(session)
            assert counts["accounts"] > 0
            assert counts["institutions"] > 0
            for table in ("transactions", "budgets", "categories", "planned_transactions"):
                assert counts[table] == 0, table

    asyncio.run(_check())


def test_cli_and_registry_produce_the_same_dataset(tmp_path: Path, file_db: str) -> None:
    """Covers: KAL-PLT-008"""
    cli_db = f"sqlite+aiosqlite:///{tmp_path / 'cli.db'}"
    proc = _run_seed_cli(tmp_path, cli_db)
    assert proc.returncode == 0, proc.stderr or proc.stdout

    async def _check() -> None:
        async with _open_session(file_db) as registry, _open_session(cli_db) as cli:
            await seed_all(registry)
            assert await _counts(cli) == await _counts(registry)

    asyncio.run(_check())


def test_the_cli_is_idempotent_too(tmp_path: Path) -> None:
    """Covers: KAL-PLT-006"""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'twice.db'}"
    first = _run_seed_cli(tmp_path, db_url)
    assert first.returncode == 0, first.stderr or first.stdout

    async def _counts_now() -> dict[str, int]:
        async with _open_session(db_url) as session:
            return await _counts(session)

    before = asyncio.run(_counts_now())
    second = _run_seed_cli(tmp_path, db_url)
    assert second.returncode == 0, second.stderr or second.stdout
    assert "left alone" in second.stdout
    assert asyncio.run(_counts_now()) == before


def test_replace_rewrites_the_dataset_with_foreign_keys_enforced(file_db: str) -> None:
    """Covers: KAL-PLT-009"""

    async def _check() -> None:
        async with _open_session(file_db) as session:
            await seed_all(session)
            before = await _counts(session)

            # Deleting the categories and accounts a live ledger points at is
            # an integrity error, not a fresh start: the whole dataset has to
            # come out in reverse dependency order first.
            await seed_all(session, replace=True)

            assert await _counts(session) == before

    asyncio.run(_check())


def test_replacing_one_feature_takes_what_stands_on_it(file_db: str) -> None:
    """Covers: KAL-PLT-009"""

    async def _check() -> None:
        async with _open_session(file_db) as session:
            await seed_all(session)
            before = await _counts(session)
            assets_before = {
                asset.id: asset.name
                for asset in (await session.execute(select(Asset))).scalars().all()
            }

            outcomes = await seed_features(session, ["accounts"], replace=True)

            # The ledger, the plan, the funds and the card all hang off the
            # accounts, so they are rebuilt with them.
            rewritten = {outcome.key for outcome in outcomes if not outcome.skipped}
            assert {"accounts", "transactions", "planned", "reserve_funds"} <= rewritten
            assert await _counts(session) == before

            # Assets stand on nothing and were not asked for — untouched.
            assets_after = {
                asset.id: asset.name
                for asset in (await session.execute(select(Asset))).scalars().all()
            }
            assert assets_after == assets_before

    asyncio.run(_check())


def test_cli_replace_survives_a_seeded_database(tmp_path: Path) -> None:
    """Covers: KAL-PLT-009

    End to end through ``scripts/seed.py``, which opens its session through
    ``kaleta.db.session`` and therefore runs with the app's real PRAGMAs.
    """
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'replace.db'}"
    first = _run_seed_cli(tmp_path, db_url)
    assert first.returncode == 0, first.stderr or first.stdout

    async def _counts_now() -> dict[str, int]:
        async with _open_session(db_url) as session:
            return await _counts(session)

    before = asyncio.run(_counts_now())
    again = _run_seed_cli(tmp_path, db_url, "--replace")
    assert again.returncode == 0, again.stderr or again.stdout
    assert asyncio.run(_counts_now()) == before


def test_debug_report_is_markdown_without_secrets() -> None:
    """Covers: KAL-SET-029"""
    markdown = sections_as_markdown(build_sections(storage_keys={"language": "str"}))

    assert markdown.startswith("## Kaleta debug info")
    assert markdown.count("\n") > 10
    assert "### Versions" in markdown
    assert f"| secret_key | `{MASK}` |" in markdown

    # The value actually in force must not appear anywhere in the report — not
    # under its own key and not inside a database URL.
    if settings.secret_key:
        assert settings.secret_key not in markdown
