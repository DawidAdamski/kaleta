# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for ScheduledBackupService VACUUM INTO + retention."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from kaleta.config import settings
from kaleta.services.scheduled_backup_service import ScheduledBackupService


def _seed_sqlite(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE demo (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO demo (name) VALUES ('kaleta')")
        conn.commit()
    finally:
        conn.close()


class TestScheduledBackupService:
    def test_create_backup_writes_timestamped_db(self, tmp_path: Path) -> None:
        """Covers: KAL-SET-017"""
        source = tmp_path / "source.db"
        backup_dir = tmp_path / "backups"
        _seed_sqlite(source)

        svc = ScheduledBackupService(
            db_url=f"sqlite+aiosqlite:///{source}",
            backup_dir=backup_dir,
            retain=7,
        )
        created = svc.create_backup()
        assert created is not None
        assert created.name.startswith("kaleta-")
        assert created.suffix == ".db"
        assert created.is_file()

        verify = sqlite3.connect(str(created))
        try:
            row = verify.execute("SELECT name FROM demo").fetchone()
        finally:
            verify.close()
        assert row == ("kaleta",)

    def test_retention_keeps_exactly_k(self, tmp_path: Path) -> None:
        """Covers: KAL-SET-017 — retain K of 2 after three runs."""
        source = tmp_path / "source.db"
        backup_dir = tmp_path / "backups"
        _seed_sqlite(source)

        svc = ScheduledBackupService(
            db_url=f"sqlite+aiosqlite:///{source}",
            backup_dir=backup_dir,
            retain=2,
        )
        for _ in range(3):
            path = svc.run_once()
            assert path is not None
            # Ensure distinct mtimes for stable newest-first ordering.
            time.sleep(0.05)

        remaining = svc.list_backups()
        assert len(remaining) == 2

    def test_skips_memory_and_postgres(self, tmp_path: Path) -> None:
        mem = ScheduledBackupService(
            db_url="sqlite+aiosqlite:///:memory:",
            backup_dir=tmp_path,
            retain=1,
        )
        assert mem.resolve_sqlite_path() is None
        assert mem.create_backup() is None

        pg = ScheduledBackupService(
            db_url="postgresql+asyncpg://localhost/kaleta",
            backup_dir=tmp_path,
            retain=1,
        )
        assert pg.resolve_sqlite_path() is None
        assert pg.create_backup() is None

    def test_from_active_config_prefers_config_json_over_settings(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Covers: KAL-SET-023"""
        active = tmp_path / "active.db"
        default = tmp_path / "kaleta.db"
        backup_dir = tmp_path / "backups"
        _seed_sqlite(active)
        # Default path exists but holds different data — must not be snapshotted.
        conn = sqlite3.connect(str(default))
        try:
            conn.execute("CREATE TABLE demo (id INTEGER PRIMARY KEY, name TEXT)")
            conn.execute("INSERT INTO demo (name) VALUES ('wrong')")
            conn.commit()
        finally:
            conn.close()

        monkeypatch.setattr(settings, "db_url", f"sqlite+aiosqlite:///{default}")
        monkeypatch.setattr(settings, "backup_dir", str(backup_dir))
        monkeypatch.setattr(settings, "backup_retain", 7)
        monkeypatch.setattr(
            "kaleta.config.setup_config.get_db_url",
            lambda: f"sqlite+aiosqlite:///{active}",
        )

        svc = ScheduledBackupService.from_active_config()
        created = svc.run_once()
        assert created is not None
        assert created.is_file()

        verify = sqlite3.connect(str(created))
        try:
            row = verify.execute("SELECT name FROM demo").fetchone()
        finally:
            verify.close()
        assert row == ("kaleta",)

    def test_from_active_config_falls_back_to_settings(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        source = tmp_path / "env-default.db"
        backup_dir = tmp_path / "backups"
        _seed_sqlite(source)

        monkeypatch.setattr(settings, "db_url", f"sqlite+aiosqlite:///{source}")
        monkeypatch.setattr(settings, "backup_dir", str(backup_dir))
        monkeypatch.setattr(settings, "backup_retain", 3)
        monkeypatch.setattr("kaleta.config.setup_config.get_db_url", lambda: None)

        svc = ScheduledBackupService.from_active_config()
        created = svc.run_once()
        assert created is not None
        assert created.parent == backup_dir
