# SPDX-License-Identifier: AGPL-3.0-or-later
"""Session scope helpers for UI callers that must not import kaleta.db directly."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.db import AsyncSessionFactory


async def with_session[T](fn: Callable[[AsyncSession], Awaitable[T]]) -> T:
    """Open a DB session, invoke ``fn(session)``, and return its result."""
    async with AsyncSessionFactory() as session:
        return await fn(session)


async def with_public_session[T](fn: Callable[[AsyncSession], Awaitable[T]]) -> T:
    """Like :func:`with_session`, on the registry's schema (the instance's shared tables)."""
    async with AsyncSessionFactory.public() as session:
        return await fn(session)
