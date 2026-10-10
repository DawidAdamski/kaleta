# SPDX-License-Identifier: AGPL-3.0-or-later
"""A registry database of a test's own (ADR-35, ADR-38).

On a companion of the suite's PostgreSQL database (``<database>_registry``,
ADR-38), where tenants are real schemas: each test starts from an empty
registry, migrated by ``alembic_public/``, and the suite family's database is
never touched. The shared session proxy is pointed there for the duration,
then put back exactly as it was: other tests use the same proxy.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from kaleta.config import settings
from kaleta.db import AsyncSessionFactory
from kaleta.db.base import Base, PublicBase
from kaleta.db.tenant_context import install_tenant_resolver, set_tenant
from kaleta.db.tenant_schemas import quote_schema
from kaleta.models import nbp_rate as _nbp_rate  # noqa: F401 — registers public.nbp_rates
from kaleta.models import tenant as _tenant  # noqa: F401 — registers the registry tables
from kaleta.schemas.identity import Identity
from kaleta.services.setup_service import _sync_url, upgrade_public_to_head
from tests.suite_database import companion_database_url

_registry_url: str | None = None


def registry_database_url() -> str:
    """This process's companion database for registry tests, created on first use."""
    global _registry_url
    if _registry_url is None:
        _registry_url = companion_database_url("registry")
    return _registry_url


def identity(n: int, *, verified: bool = True, email: str | None = None) -> Identity:
    """A GoTrue-shaped identity: a UUID-like subject and an e-mail."""
    return Identity(
        subject=f"00000000-0000-4000-8000-{n:012d}",
        email=email or f"member{n}@example.com",
        email_verified=verified,
    )


def _drop_postgres_multi_tenant_state(url: str) -> None:
    """Leave the companion database with no registry and no tenant schema."""
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
            # Every registry table the models know, so a new one cannot be missed.
            tables = [t.name for t in reversed(PublicBase.metadata.sorted_tables)]
            for table in (*tables, "alembic_version_public"):
                conn.execute(text(f"DROP TABLE IF EXISTS public.{table} CASCADE"))
    finally:
        engine.dispose()


@asynccontextmanager
async def multi_tenant_database(
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
    loop = asyncio.get_running_loop()
    url = await loop.run_in_executor(None, registry_database_url)
    saved = (settings.auth_backend, settings.db_url, settings.encryption)
    await loop.run_in_executor(None, _drop_postgres_multi_tenant_state, url)
    await loop.run_in_executor(None, upgrade_public_to_head, url)
    # Attribute assignment skips the settings validator on purpose: these
    # tests fake the identity provider, so no Supabase URL exists.
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
        settings.auth_backend, settings.db_url, settings.encryption = saved
        AsyncSessionFactory.configure(settings.db_url, debug=settings.debug)
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
        engine = create_async_engine(self._db_url)
        async with engine.begin() as conn:
            await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {quote_schema(schema)}"))
            translated = await conn.execution_options(schema_translate_map={None: schema})
            await translated.run_sync(Base.metadata.create_all)
        await engine.dispose()

    async def drop(self, schema: str) -> None:
        self.dropped.append(schema)
        engine = create_async_engine(self._db_url)
        async with engine.begin() as conn:
            await conn.execute(text(f"DROP SCHEMA IF EXISTS {quote_schema(schema)} CASCADE"))
        await engine.dispose()

    async def pending(self, schema: str) -> bool:
        return False


def public_session() -> AsyncSession:
    return AsyncSessionFactory.public()
