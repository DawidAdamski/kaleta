# SPDX-License-Identifier: AGPL-3.0-or-later
"""Database session factory — supports runtime reconfiguration via proxy pattern.

All modules that import `AsyncSessionFactory` share the same proxy object.
Calling `AsyncSessionFactory.configure(url)` replaces the internal factory
without requiring importers to re-import anything.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from kaleta.config import settings
from kaleta.db.tenant_context import TenantContextMissingError, current_tenant
from kaleta.db.tenant_schemas import attach_sqlite_schemas


def _register_sqlite_pragmas(sync_engine: Engine) -> None:
    """Apply durability/integrity PRAGMAs on every new SQLite connection."""

    @event.listens_for(sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection: Any, _connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


class _SessionProxy:
    """Thin proxy around ``async_sessionmaker`` that can be reconfigured at runtime.

    In ``KALETA_TENANCY=multi`` every session is bound to the current tenant's
    schema through ``schema_translate_map`` — on PostgreSQL one engine and one
    pool for all tenants, the schema rewritten into each compiled statement,
    never a ``SET search_path`` (ADR-35). On SQLite each tenant has an engine
    that attaches only its own file (see ``attach_sqlite_schemas``). No tenant
    known means no session.
    """

    def __init__(self) -> None:
        self._engine: AsyncEngine | None = None
        self._factory: async_sessionmaker[AsyncSession] | None = None
        self._multi = False
        self._url = ""
        self._debug = False
        self._tenant_engines: dict[str, AsyncEngine] = {}
        self._init(settings.db_url, debug=settings.debug)

    def _init(self, url: str, debug: bool = False) -> None:
        self._multi = settings.tenancy == "multi"
        self._url = url
        self._debug = debug
        self._tenant_engines = {}
        self._engine = self._create_engine(tenant=None)
        self._factory = async_sessionmaker(
            bind=self._engine,
            expire_on_commit=False,
            autoflush=False,
        )

    def _create_engine(self, *, tenant: str | None) -> AsyncEngine:
        url = self._url
        if "sqlite" not in url:
            return create_async_engine(url, echo=self._debug)
        connect_args: dict[str, Any] = {"check_same_thread": False}
        if not self._multi:
            engine = create_async_engine(url, echo=self._debug, connect_args=connect_args)
            _register_sqlite_pragmas(engine.sync_engine)
            return engine
        # Multi-tenant SQLite (dev/test): an engine per tenant, each attaching
        # only `public` and its own file, so no connection can name two
        # tenants. No pooling — a tenant file can be created or dropped while
        # the process runs, and a pooled connection would outlive that.
        engine = create_async_engine(
            url, echo=self._debug, connect_args=connect_args, poolclass=NullPool
        )
        _register_sqlite_pragmas(engine.sync_engine)
        attach_sqlite_schemas(engine.sync_engine, url, tenant=tenant)
        return engine

    def configure(self, url: str, debug: bool = False) -> None:
        """Replace the underlying engine and session factory with a new database URL."""
        self._init(url, debug=debug)

    async def dispose(self) -> None:
        """Close all pooled connections on the current engine."""
        if self._engine is not None:
            for bound in self._tenant_engines.values():
                if bound.sync_engine.pool is not self._engine.sync_engine.pool:
                    await bound.dispose()
            await self._engine.dispose()
            self._engine = None
            self._factory = None
            self._tenant_engines = {}

    @property
    def multi_tenant(self) -> bool:
        return self._multi

    def _tenant_engine(self, engine: AsyncEngine, schema: str) -> AsyncEngine:
        bound = self._tenant_engines.get(schema)
        if bound is None:
            base = self._create_engine(tenant=schema) if "sqlite" in self._url else engine
            bound = base.execution_options(schema_translate_map={None: schema})
            self._tenant_engines[schema] = bound
        return bound

    def __call__(self) -> AsyncSession:
        if self._factory is None or self._engine is None:
            raise RuntimeError("Database not configured. Call configure() first.")
        if not self._multi:
            return self._factory()
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
