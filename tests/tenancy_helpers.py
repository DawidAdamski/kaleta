# SPDX-License-Identifier: AGPL-3.0-or-later
"""A multi-tenant database for tests (ADR-35, ``KALETA_TENANCY=multi``).

SQLite by default — every schema a file next to the main one, attached under
its name — or the PostgreSQL database in ``KALETA_DB_URL`` when that is one
(the CI ``postgres`` jobs), where schemas are real schemas. Either way the
registry is migrated by ``alembic_public/`` and the shared session proxy is
switched to multi-tenant mode for the duration, then put back exactly as it
was: other tests use the same proxy.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from kaleta.config import settings
from kaleta.db import AsyncSessionFactory
from kaleta.db.base import Base
from kaleta.db.tenant_context import install_tenant_resolver, set_tenant
from kaleta.db.tenant_schemas import is_sqlite_url, quote_schema, sqlite_schema_file
from kaleta.schemas.identity import Identity
from kaleta.services.setup_service import _sync_url, upgrade_public_to_head

POSTGRES_URL = os.environ.get("KALETA_DB_URL", "")
USE_POSTGRES = POSTGRES_URL.startswith("postgresql")


def identity(n: int, *, verified: bool = True, email: str | None = None) -> Identity:
    """A GoTrue-shaped identity: a UUID-like subject and an e-mail."""
    return Identity(
        subject=f"00000000-0000-4000-8000-{n:012d}",
        email=email or f"member{n}@example.com",
        email_verified=verified,
    )


def _drop_postgres_multi_tenant_state(url: str) -> None:
    """Leave the shared CI database as the single-tenant tests expect it."""
    engine = create_engine(_sync_url(url))
    try:
        with engine.begin() as conn:
            schemas = conn.execute(
                text(
                    "SELECT schema_name FROM information_schema.schemata WHERE schema_name ~ '^t_'"
                )
            ).scalars()
            for schema in list(schemas):
                conn.execute(text(f"DROP SCHEMA {quote_schema(schema)} CASCADE"))
            for table in (
                "tenant_invites",
                "tenant_members",
                "tenants",
                "local_identities",
                "instance_settings",
                "alembic_version_public",
            ):
                conn.execute(text(f"DROP TABLE IF EXISTS public.{table} CASCADE"))
    finally:
        engine.dispose()


@asynccontextmanager
async def multi_tenant_database(
    tmp_path: Path,
    *,
    encryption: Literal["off", "passphrase"] = "off",
    auth_backend: Literal["supabase", "local"] = "supabase",
) -> AsyncIterator[str]:
    """Yield the URL of a fresh multi-tenant database with its registry migrated.

    ``encryption`` is ``off`` unless a test asks: these tests are about schemas
    and sign-in, and a hosted instance's field encryption has tests of its own
    that pass ``"passphrase"`` and unlock a key first. ``auth_backend="local"``
    is the registry layout with local logins (ADR-38).
    """
    url = POSTGRES_URL if USE_POSTGRES else f"sqlite+aiosqlite:///{tmp_path / 'hosted.db'}"
    saved = (settings.tenancy, settings.auth_backend, settings.db_url, settings.encryption)
    loop = asyncio.get_running_loop()
    if USE_POSTGRES:
        await loop.run_in_executor(None, _drop_postgres_multi_tenant_state, url)
    await loop.run_in_executor(None, upgrade_public_to_head, url)
    # Attribute assignment skips the settings validator on purpose: these
    # tests fake the identity provider, so no Supabase URL exists.
    settings.tenancy = "multi"
    settings.auth_backend = auth_backend
    settings.db_url = url
    settings.encryption = encryption
    AsyncSessionFactory.configure(url)
    set_tenant(None)
    try:
        yield url
    finally:
        set_tenant(None)
        install_tenant_resolver(None)
        await AsyncSessionFactory.dispose()
        settings.tenancy, settings.auth_backend, settings.db_url, settings.encryption = saved
        AsyncSessionFactory.configure(settings.db_url, debug=settings.debug)
        if USE_POSTGRES:
            await loop.run_in_executor(None, _drop_postgres_multi_tenant_state, url)


class MetadataProvisioner:
    """Builds a tenant schema from ``Base.metadata`` — fast, for unit tests.

    The real provisioner runs every Alembic migration; that is what the
    integration tests use. Counts its calls so idempotency can be asserted.
    """

    def __init__(self, db_url: str, *, fail_first: bool = False) -> None:
        self._db_url = db_url
        self._fail_next = fail_first
        self.created: list[str] = []
        self.dropped: list[str] = []

    async def create(self, schema: str) -> None:
        if self._fail_next:
            self._fail_next = False
            msg = "simulated crash while building the schema"
            raise RuntimeError(msg)
        self.created.append(schema)
        if is_sqlite_url(self._db_url):
            engine = create_async_engine(
                "sqlite+aiosqlite:///" + str(sqlite_schema_file(self._db_url, schema))
            )
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        else:
            engine = create_async_engine(self._db_url)
            async with engine.begin() as conn:
                await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {quote_schema(schema)}"))
                translated = await conn.execution_options(schema_translate_map={None: schema})
                await translated.run_sync(Base.metadata.create_all)
        await engine.dispose()

    async def drop(self, schema: str) -> None:
        self.dropped.append(schema)
        if is_sqlite_url(self._db_url):
            path = sqlite_schema_file(self._db_url, schema)
            path.unlink(missing_ok=True)
            return
        engine = create_async_engine(self._db_url)
        async with engine.begin() as conn:
            await conn.execute(text(f"DROP SCHEMA IF EXISTS {quote_schema(schema)} CASCADE"))
        await engine.dispose()

    async def pending(self, schema: str) -> bool:
        return False


def public_session() -> AsyncSession:
    return AsyncSessionFactory.public()
