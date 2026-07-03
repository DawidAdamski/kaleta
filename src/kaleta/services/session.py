"""Session scope helper for UI callers that must not import kaleta.db directly."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.db import AsyncSessionFactory


async def with_session[T](fn: Callable[[AsyncSession], Awaitable[T]]) -> T:
    """Open a DB session, invoke ``fn(session)``, and return its result."""
    async with AsyncSessionFactory() as session:
        return await fn(session)
