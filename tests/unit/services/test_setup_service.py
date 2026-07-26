# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for setup_service schema ensure / migrate-on-start."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from alembic import command
from kaleta.config import settings
from kaleta.exceptions import MigrationError
from kaleta.services.setup_service import (
    _alembic_config,
    current_revision,
    ensure_schema_current,
    head_revision,
    upgrade_to_head,
)


def _downgrade_one(db_url: str) -> None:
    os.environ["KALETA_MIGRATE_URL"] = db_url
    try:
        command.downgrade(_alembic_config(), "-1")
    finally:
        os.environ.pop("KALETA_MIGRATE_URL", None)


class TestEnsureSchemaCurrent:
    def test_noop_when_already_at_head(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db_path = tmp_path / "at-head.db"
        backup_dir = tmp_path / "backups"
        monkeypatch.setattr(settings, "backup_dir", str(backup_dir))
        db_url = f"sqlite+aiosqlite:///{db_path}"

        upgrade_to_head(db_url)
        assert current_revision(db_url) == head_revision()

        ensure_schema_current(db_url)
        assert current_revision(db_url) == head_revision()
        assert list(backup_dir.glob("kaleta-*.db")) == []

    def test_upgrades_behind_db_with_safety_copy(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Covers: KAL-SET-019"""
        db_path = tmp_path / "behind.db"
        backup_dir = tmp_path / "backups"
        monkeypatch.setattr(settings, "backup_dir", str(backup_dir))
        db_url = f"sqlite+aiosqlite:///{db_path}"

        upgrade_to_head(db_url)
        head = head_revision()
        _downgrade_one(db_url)
        behind = current_revision(db_url)
        assert behind is not None
        assert behind != head

        ensure_schema_current(db_url)

        assert current_revision(db_url) == head
        backups = list(backup_dir.glob("kaleta-*.db"))
        assert len(backups) == 1
        assert backups[0].is_file()

    def test_unknown_revision_refuses(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db_path = tmp_path / "unknown.db"
        backup_dir = tmp_path / "backups"
        monkeypatch.setattr(settings, "backup_dir", str(backup_dir))
        db_url = f"sqlite+aiosqlite:///{db_path}"

        upgrade_to_head(db_url)
        engine = create_engine(f"sqlite:///{db_path}")
        try:
            with engine.begin() as conn:
                conn.execute(text("UPDATE alembic_version SET version_num = 'notarealrevision000'"))
        finally:
            engine.dispose()

        with pytest.raises(MigrationError, match="unknown alembic revision"):
            ensure_schema_current(db_url)
        assert list(backup_dir.glob("kaleta-*.db")) == []
