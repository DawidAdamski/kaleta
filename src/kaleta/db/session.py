# SPDX-License-Identifier: AGPL-3.0-or-later
"""Database session factory — supports runtime reconfiguration via proxy pattern.

All modules that import `AsyncSessionFactory` share the same proxy object.
Calling `AsyncSessionFactory.configure(url)` replaces the internal factory
without requiring importers to re-import anything.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from kaleta.config import settings
from kaleta.db.tenant_context import TenantContextMissingError, current_tenant

#: Connections per process on PostgreSQL: Supabase's pooler counts every
#: client connection against the project's limit, so a replica takes at most
#: ten (docs/deployment.md, "Database").
_PG_POOL_SIZE = 5
_PG_MAX_OVERFLOW = 5


def _asyncpg_connect_args() -> dict[str, Any]:
    """No prepared statement may outlive its transaction.

    A transaction-mode pooler (Supabase's, on port 6543) hands each transaction
    whichever server connection is free, so a statement asyncpg prepared on
    one is unknown on the next. No statement cache, and a fresh name per
    statement, keep that from ever mattering; on a direct connection it costs a
    re-parse per query and nothing else.
    """
    return {
        "statement_cache_size": 0,
        "prepared_statement_name_func": lambda: f"__kaleta_{uuid.uuid4().hex}__",
    }


class _SessionProxy:
    """Thin proxy around ``async_sessionmaker`` that can be reconfigured at runtime.

    Every session is bound to the current family's schema through
    ``schema_translate_map`` — one engine and one pool for all tenants, the
    schema rewritten into each compiled statement, never a ``SET search_path``
    (ADR-35). No tenant known means no session.
    """

    def __init__(self) -> None:
        self._engine: AsyncEngine | None = None
        self._factory: async_sessionmaker[AsyncSession] | None = None
        self._url = ""
        self._debug = False
        self._tenant_engines: dict[str, AsyncEngine] = {}
        self._init(settings.db_url, debug=settings.debug)

    def _init(self, url: str, debug: bool = False) -> None:
        self._url = url
        self._debug = debug
        self._tenant_engines = {}
        self._engine = self._create_engine()
        self._factory = async_sessionmaker(
            bind=self._engine,
            expire_on_commit=False,
            autoflush=False,
        )

    def _create_engine(self) -> AsyncEngine:
        url = self._url
        connect = _asyncpg_connect_args() if url.startswith("postgresql+asyncpg") else {}
        return create_async_engine(
            url,
            echo=self._debug,
            connect_args=connect,
            pool_size=_PG_POOL_SIZE,
            max_overflow=_PG_MAX_OVERFLOW,
            pool_pre_ping=True,
        )

    def configure(self, url: str, debug: bool = False) -> None:
        """Replace the underlying engine and session factory with a new database URL."""
        self._init(url, debug=debug)

    async def dispose(self) -> None:
        """Close all pooled connections on the current engine."""
        if self._engine is not None:
            # The tenants' engines are views of this one: one pool between them.
            await self._engine.dispose()
            self._engine = None
            self._factory = None
            self._tenant_engines = {}

    def _tenant_engine(self, engine: AsyncEngine, schema: str) -> AsyncEngine:
        bound = self._tenant_engines.get(schema)
        if bound is None:
            bound = engine.execution_options(schema_translate_map={None: schema})
            self._tenant_engines[schema] = bound
        return bound

    def __call__(self) -> AsyncSession:
        if self._factory is None or self._engine is None:
            raise RuntimeError("Database not configured. Call configure() first.")
        ctx = current_tenant()
        if ctx is None:
            raise TenantContextMissingError(
                "No tenant context for this request; refusing to open a tenant-schema session"
            )
        return self._factory(bind=self._tenant_engine(self._engine, ctx.schema))

    def public(self) -> AsyncSession:
        """A session with no tenant schema: the registry, health probes.

        Registry models name ``public`` themselves; tenant tables are simply
        not there, so a query for one fails rather than finding someone's rows.
        """
        if self._factory is None:
            raise RuntimeError("Database not configured. Call configure() first.")
        return self._factory()


AsyncSessionFactory: _SessionProxy = _SessionProxy()


async def get_session() -> AsyncGenerator[AsyncSession]:
    """FastAPI dependency that yields a database session."""
    async with AsyncSessionFactory() as session:
        yield session
