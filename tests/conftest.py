# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared pytest fixtures for all tests."""

import os

from tests.suite_database import suite_database_env_or_exit

# Allow default secret key during test runs (see kaleta.config.settings).
os.environ.setdefault("KALETA_DEBUG", "true")
# The suite runs on PostgreSQL only (ADR-38); under ``pytest -n`` each worker
# gets a database of its own. The settings read KALETA_DB_URL on import, so
# this precedes every kaleta import.
os.environ.update(suite_database_env_or_exit())

import pytest
import pytest_asyncio
from argon2 import PasswordHasher
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
from kaleta.auth import session as session_mod
from kaleta.config import settings
from kaleta.crypto import DataKey, generate_dek, key_ring
from kaleta.db.base import Base
from kaleta.db.types import install_data_key_resolver
from kaleta.models.currency_rate import CurrencyRate  # noqa: F401
from kaleta.models.institution import Institution  # noqa: F401
from kaleta.services.setup_service import upgrade_to_head

_POSTGRES_URL = os.environ["KALETA_DB_URL"]
# Idempotent: a fresh database is built, a current one costs a version check.
upgrade_to_head(_POSTGRES_URL)
_postgres_truncated = False


def make_session_factory(bind: AsyncEngine | AsyncConnection):
    """Build a session factory; savepoints keep service commits inside the test's transaction."""
    return async_sessionmaker(
        bind,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )


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
    """A PostgreSQL connection whose transaction is rolled back after the test."""
    engine = create_async_engine(_POSTGRES_URL, echo=False, poolclass=NullPool)
    await _truncate_postgres_once(engine)
    async with engine.connect() as conn:
        await conn.begin()
        yield conn
        await conn.rollback()
    await engine.dispose()


@pytest_asyncio.fixture
async def sqlite_session():
    """An in-memory SQLite session, for the SQLite-only code that is still in ``src``.

    Goes with that code (``postgres-only`` part B3); nothing else uses it.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        yield s
    await engine.dispose()


@pytest_asyncio.fixture
async def session(db_engine):
    """Async SQLAlchemy session backed by the test database."""
    factory = make_session_factory(db_engine)
    async with factory() as s:
        yield s


#: The data key every test runs under when the suite is started with
#: ``KALETA_ENCRYPTION=passphrase`` — the whole suite then reads and writes
#: ciphertext, which is the acceptance run of ``hosted-field-encryption``.
TEST_DATA_KEY = DataKey(generate_dek())


#: The real lookup, for tests of the locked path to put back (``real_unlock``).
REAL_SESSION_DATA_KEY = session_mod.session_data_key


class _CheapPasswordHasher(PasswordHasher):
    """Argon2id at the cost the KDF tests use (``_FAST_KDF``), not 64 MiB × 3.

    Every MFA enrolment hashes ten recovery codes; at production cost that was
    a sixth of the suite's time (test-suite-speed audit). The hash format and
    verification path are the real ones; only the cost parameters differ.
    """

    def __init__(self) -> None:
        super().__init__(time_cost=1, memory_cost=8 * 1024, parallelism=1)


@pytest.fixture(autouse=True)
def _cheap_password_hashing(monkeypatch: pytest.MonkeyPatch) -> None:
    for module in (
        "kaleta.services.mfa_service",
        "kaleta.services.auth_service",
        "kaleta.services.local_identity_service",
    ):
        monkeypatch.setattr(f"{module}.PasswordHasher", _CheapPasswordHasher)


@pytest.fixture(autouse=True)
def _unlocked_test_keyring(monkeypatch: pytest.MonkeyPatch):
    """Stand in for an unlocked session: services get ``TEST_DATA_KEY``.

    Only while encryption is on. Database work outside a browser session gets
    it from the resolver; a browser session (the page guard, the API's cookie
    path, a hosted ``TenantContext``) counts as unlocked with it. API bearer
    requests get neither — they ride on a ``key_ring`` entry for their member,
    which ``tests/integration/conftest.py`` puts there for the API user — so
    the bearer ``423`` path stays the real one. Tests of the locked browser
    path take ``real_unlock``.
    """
    if not settings.encryption_enabled:
        yield
        return
    install_data_key_resolver(lambda: TEST_DATA_KEY)
    monkeypatch.setattr(session_mod, "session_data_key", lambda: TEST_DATA_KEY)
    monkeypatch.setattr("kaleta.api.deps.session_data_key", lambda: TEST_DATA_KEY)
    try:
        yield
    finally:
        install_data_key_resolver(None)
        key_ring.clear()


@pytest.fixture
def real_unlock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Undo ``_unlocked_test_keyring``'s browser stand-in: sessions unlock for real."""
    monkeypatch.setattr(session_mod, "session_data_key", REAL_SESSION_DATA_KEY)
    monkeypatch.setattr("kaleta.api.deps.session_data_key", REAL_SESSION_DATA_KEY)
