# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared pytest fixtures for all tests."""

import os

# Allow default secret key during test runs (see kaleta.config.settings).
os.environ.setdefault("KALETA_DEBUG", "true")

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

# Import models so Base.metadata includes every table for postgres TRUNCATE.
import kaleta.models  # noqa: F401
from kaleta.db.base import Base
from kaleta.models.currency_rate import CurrencyRate  # noqa: F401
from kaleta.models.institution import Institution  # noqa: F401

_POSTGRES_URL = os.environ.get("KALETA_DB_URL", "")
_USE_POSTGRES = _POSTGRES_URL.startswith("postgresql")
_postgres_truncated = False


def make_session_factory(bind: AsyncEngine | AsyncConnection):
    """Build a session factory; postgres tests use savepoints around service commits."""
    if _USE_POSTGRES:
        return async_sessionmaker(
            bind,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
    return async_sessionmaker(bind, expire_on_commit=False)


async def _truncate_postgres_once(engine: AsyncEngine) -> None:
    global _postgres_truncated
    if _postgres_truncated:
        return
    table_names = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
    if not table_names:
        _postgres_truncated = True
        return
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))
    _postgres_truncated = True


@pytest_asyncio.fixture
async def db_engine():
    """In-memory SQLite per test, or a rolled-back postgres connection."""
    if _USE_POSTGRES:
        engine = create_async_engine(_POSTGRES_URL, echo=False, poolclass=NullPool)
        await _truncate_postgres_once(engine)
        async with engine.connect() as conn:
            await conn.begin()
            yield conn
            await conn.rollback()
        await engine.dispose()
        return

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session(db_engine):
    """Async SQLAlchemy session backed by the test database."""
    factory = make_session_factory(db_engine)
    async with factory() as s:
        yield s
