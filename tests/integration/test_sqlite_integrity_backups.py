# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration coverage for scheduled backups, SQLite pragmas, and integrity.

Covers: KAL-SET-017, KAL-SET-018, KAL-INT-001, KAL-INT-002
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.db.session import AsyncSessionFactory
from kaleta.services.integrity_service import IntegrityService
from kaleta.services.scheduled_backup_service import ScheduledBackupService
from tests.conftest import _USE_POSTGRES


@pytest.mark.skipif(_USE_POSTGRES, reason="SQLite-only scheduled VACUUM backups")
def test_scheduled_backup_retention_keeps_two(tmp_path: Path) -> None:
    """Covers: KAL-SET-017"""
    import sqlite3

    source = tmp_path / "live.db"
    backup_dir = tmp_path / "backups"
    conn = sqlite3.connect(str(source))
    try:
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
        conn.commit()
    finally:
        conn.close()

    svc = ScheduledBackupService(
        db_url=f"sqlite+aiosqlite:///{source}",
        backup_dir=backup_dir,
        retain=2,
    )
    for _ in range(3):
        assert svc.run_once() is not None
        time.sleep(0.05)

    assert len(svc.list_backups()) == 2
    assert all(p.name.startswith("kaleta-") and p.suffix == ".db" for p in svc.list_backups())


@pytest.mark.skipif(_USE_POSTGRES, reason="SQLite-only connect pragmas")
@pytest.mark.asyncio
async def test_connect_pragmas_on_session_factory(tmp_path: Path) -> None:
    """Covers: KAL-SET-018"""
    db_path = tmp_path / "pragmas.db"
    AsyncSessionFactory.configure(f"sqlite+aiosqlite:///{db_path}", debug=False)
    try:
        async with AsyncSessionFactory() as session:
            assert (await session.execute(text("PRAGMA foreign_keys"))).scalar() == 1
            journal = (await session.execute(text("PRAGMA journal_mode"))).scalar()
            assert str(journal).lower() == "wal"
            assert (await session.execute(text("PRAGMA busy_timeout"))).scalar() == 5000
            assert (await session.execute(text("PRAGMA synchronous"))).scalar() == 1
    finally:
        await AsyncSessionFactory.dispose()


@pytest.mark.skipif(_USE_POSTGRES, reason="SQLite-only foreign_key_check")
@pytest.mark.asyncio
async def test_integrity_clean_and_orphan(session: AsyncSession) -> None:
    """Covers: KAL-INT-001, KAL-INT-002"""
    svc = IntegrityService(session)
    assert await svc.foreign_key_check() == []

    await session.execute(text("PRAGMA foreign_keys=OFF"))
    await session.execute(
        text(
            "INSERT INTO accounts (name, type, balance, currency, institution_id) "
            "VALUES ('Orphan', 'checking', 0, 'PLN', 99999)"
        )
    )
    await session.commit()
    await session.execute(text("PRAGMA foreign_keys=ON"))

    violations = await svc.foreign_key_check()
    assert any(v.table == "accounts" and v.parent == "institutions" for v in violations)
