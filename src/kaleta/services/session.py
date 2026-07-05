# SPDX-License-Identifier: AGPL-3.0-or-later
"""Session scope helper for UI callers that must not import kaleta.db directly."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.db import AsyncSessionFactory


async def with_session[T](fn: Callable[[AsyncSession], Awaitable[T]]) -> T:
    """Open a DB session, invoke ``fn(session)``, and return its result."""
    async with AsyncSessionFactory() as session:
        return await fn(session)


async def dispose_sessions() -> None:
    """Close the shared engine and connection pool (e.g. when switching databases)."""
    await AsyncSessionFactory.dispose()
