"""Shared pytest fixtures for all tests."""

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from kaleta.db.base import Base


@pytest_asyncio.fixture
async def db_engine():
    """In-memory async SQLite engine — schema created fresh for every test."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session(db_engine):
    """Async SQLAlchemy session backed by in-memory SQLite."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as s:
        yield s
