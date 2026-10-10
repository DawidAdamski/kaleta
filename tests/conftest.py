# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared pytest fixtures for all tests."""

import os
from collections.abc import Iterator
from dataclasses import replace

from tests.suite_database import suite_database_env_or_exit

# Allow default secret key during test runs (see kaleta.config.settings).
os.environ.setdefault("KALETA_DEBUG", "true")
# Local logins in the registry (ADR-38), unless a run asks for another backend.
os.environ.setdefault("KALETA_AUTH_BACKEND", "local")
# The suite runs on PostgreSQL only (ADR-38); under ``pytest -n`` each worker
# gets a database of its own. The settings read KALETA_DB_URL on import, so
# this precedes every kaleta import.
os.environ.update(suite_database_env_or_exit())

import pytest
import pytest_asyncio
from argon2 import PasswordHasher
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
from kaleta.db import AsyncSessionFactory
from kaleta.db.base import Base
from kaleta.db.tenant_context import set_tenant
from kaleta.db.types import install_data_key_resolver
from kaleta.models.currency_rate import CurrencyRate  # noqa: F401
from kaleta.models.institution import Institution  # noqa: F401
from kaleta.models.user import User
from tests.suite_family import SUITE_EMAIL, SUITE_PASSWORD, bootstrap_suite_family  # noqa: F401

_POSTGRES_URL = os.environ["KALETA_DB_URL"]
_suite = bootstrap_suite_family(_POSTGRES_URL)
#: The family every test's ``session`` works in; see ``tests.suite_family``.
SUITE_FAMILY = _suite.context
#: Its administrator's subject (``local:<id>``).
SUITE_SUBJECT = _suite.subject


def make_session_factory(bind: AsyncEngine | AsyncConnection):
    """Build a session factory; savepoints keep service commits inside the test's transaction."""
    return async_sessionmaker(
        bind,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )


@pytest_asyncio.fixture
async def db_engine():
    """A connection to the suite family's schema, rolled back after the test.

    Statements name the family's schema the way the app's do —
    ``schema_translate_map`` — and registry models name ``public`` themselves.
    """
    engine = create_async_engine(_POSTGRES_URL, echo=False, poolclass=NullPool)
    async with engine.connect() as conn:
        await conn.execution_options(schema_translate_map={None: SUITE_FAMILY.schema})
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


def family_table(name: str) -> str:
    """``name`` qualified with the suite family's schema, for raw SQL in tests.

    The app never relies on ``search_path`` (statements carry the schema
    through ``schema_translate_map``), so neither does the test connection:
    raw SQL has to say where it looks.
    """
    return f'"{SUITE_FAMILY.schema}".{name}'


def sign_into_suite_family(storage: dict[str, object]) -> None:
    """Write the suite family into a (fake) ``app.storage.user``, as a sign-in does.

    Every authenticated session names its family; a test that builds a
    session by hand puts these next to ``SESSION_AUTHENTICATED``.
    """
    storage[session_mod.SESSION_TENANT_ID] = SUITE_FAMILY.tenant_id
    storage[session_mod.SESSION_TENANT_SCHEMA] = SUITE_FAMILY.schema
    storage[session_mod.SESSION_AUTH_SUBJECT] = SUITE_SUBJECT
    storage[session_mod.SESSION_EMAIL] = SUITE_EMAIL


@pytest.fixture(autouse=True)
def _in_the_suite_family() -> Iterator[None]:
    """Every test runs as a request does: in a family (the suite's).

    Unlocked, while encryption is on: the context carries ``TEST_DATA_KEY``,
    as an unlocked member's request does. Tests of what happens without one,
    locked, or in families of their own, set the context themselves
    (``set_tenant``, ``use_tenant``).
    """
    key = TEST_DATA_KEY if settings.encryption_enabled else None
    set_tenant(replace(SUITE_FAMILY, key_ring=key))
    try:
        yield
    finally:
        set_tenant(None)


@pytest_asyncio.fixture(autouse=True)
async def _session_pool_per_test():
    """No pooled connection outlives its test's event loop.

    Code under test opens sessions on the shared proxy too — the API resolves
    a bearer token's family in the registry — and asyncpg connections belong
    to the loop that opened them; every test has a loop of its own.
    """
    yield
    await AsyncSessionFactory.dispose()
    AsyncSessionFactory.configure(_POSTGRES_URL, debug=settings.debug)


@pytest_asyncio.fixture
async def session(db_engine):
    """Async SQLAlchemy session backed by the test database."""
    factory = make_session_factory(db_engine)
    async with factory() as s:
        yield s


@pytest_asyncio.fixture
async def suite_owner(session):
    """The suite family's owner, whose login (``SUITE_PASSWORD``) is in the registry."""
    user = await session.get(User, SUITE_FAMILY.member_user_id)
    assert user is not None
    return user


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
