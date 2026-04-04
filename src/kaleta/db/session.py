"""Database session factory — supports runtime reconfiguration via proxy pattern.

All modules that import `AsyncSessionFactory` share the same proxy object.
Calling `AsyncSessionFactory.configure(url)` replaces the internal factory
without requiring importers to re-import anything.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from kaleta.config import settings


class _SessionProxy:
    """Thin proxy around ``async_sessionmaker`` that can be reconfigured at runtime."""

    def __init__(self) -> None:
        self._engine: AsyncEngine | None = None
        self._factory: async_sessionmaker[AsyncSession] | None = None
        self._init(settings.db_url, debug=settings.debug)

    def _init(self, url: str, debug: bool = False) -> None:
        connect_args: dict[str, Any] = {"check_same_thread": False} if "sqlite" in url else {}
        self._engine = create_async_engine(url, echo=debug, connect_args=connect_args)
        self._factory = async_sessionmaker(
            bind=self._engine,
            expire_on_commit=False,
            autoflush=False,
        )

    def configure(self, url: str, debug: bool = False) -> None:
        """Replace the underlying engine and session factory with a new database URL."""
        self._init(url, debug=debug)

    async def dispose(self) -> None:
        """Close all pooled connections on the current engine."""
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._factory = None

    def __call__(self) -> AsyncSession:
        if self._factory is None:
            raise RuntimeError("Database not configured. Call configure() first.")
        return self._factory()


AsyncSessionFactory: _SessionProxy = _SessionProxy()


async def get_session() -> AsyncGenerator[AsyncSession]:
    """FastAPI dependency that yields a database session."""
    async with AsyncSessionFactory() as session:
        yield session
