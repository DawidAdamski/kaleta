# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for SQLite connect-time PRAGMAs on AsyncSessionFactory."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

from kaleta.db.session import AsyncSessionFactory


@pytest.mark.asyncio
async def test_sqlite_connect_pragmas(tmp_path: Path) -> None:
    """Covers: KAL-SET-018 — foreign_keys, WAL, busy_timeout, synchronous=NORMAL."""
    db_path = tmp_path / "pragma.db"
    url = f"sqlite+aiosqlite:///{db_path}"
    AsyncSessionFactory.configure(url, debug=False)
    try:
        async with AsyncSessionFactory() as session:
            foreign_keys = (await session.execute(text("PRAGMA foreign_keys"))).scalar()
            journal_mode = (await session.execute(text("PRAGMA journal_mode"))).scalar()
            busy_timeout = (await session.execute(text("PRAGMA busy_timeout"))).scalar()
            synchronous = (await session.execute(text("PRAGMA synchronous"))).scalar()

        assert foreign_keys == 1
        assert str(journal_mode).lower() == "wal"
        assert busy_timeout == 5000
        assert synchronous == 1
    finally:
        await AsyncSessionFactory.dispose()
