# SPDX-License-Identifier: AGPL-3.0-or-later
"""SQLite connect-time pragmas on the session proxy, until SQLite goes (postgres-only B3).

Covers: KAL-SET-018
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

from kaleta.config import settings
from kaleta.db.session import AsyncSessionFactory


@pytest.mark.asyncio
async def test_connect_pragmas_on_session_factory(tmp_path: Path) -> None:
    """Covers: KAL-SET-018"""
    db_path = tmp_path / "pragmas.db"
    AsyncSessionFactory.configure(f"sqlite+aiosqlite:///{db_path}", debug=False)
    try:
        # The registry session: the one that needs no family's file attached.
        async with AsyncSessionFactory.public() as session:
            assert (await session.execute(text("PRAGMA foreign_keys"))).scalar() == 1
            journal = (await session.execute(text("PRAGMA journal_mode"))).scalar()
            assert str(journal).lower() == "wal"
            assert (await session.execute(text("PRAGMA busy_timeout"))).scalar() == 5000
            assert (await session.execute(text("PRAGMA synchronous"))).scalar() == 1
    finally:
        await AsyncSessionFactory.dispose()
        AsyncSessionFactory.configure(settings.db_url, debug=settings.debug)
