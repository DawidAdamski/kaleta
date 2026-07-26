# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration coverage for auto-migrate on start.

Covers: KAL-SET-019
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from alembic import command
from kaleta.config import settings
from kaleta.services.setup_service import (
    _alembic_config,
    current_revision,
    ensure_schema_current,
    head_revision,
    upgrade_to_head,
)
from tests.conftest import _USE_POSTGRES


@pytest.mark.skipif(_USE_POSTGRES, reason="SQLite auto-migrate safety copy path")
def test_ensure_schema_current_upgrades_with_vacuum_safety_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Covers: KAL-SET-019"""
    db_path = tmp_path / "live.db"
    backup_dir = tmp_path / "backups"
    monkeypatch.setattr(settings, "backup_dir", str(backup_dir))
    db_url = f"sqlite+aiosqlite:///{db_path}"

    upgrade_to_head(db_url)
    head = head_revision()
    os.environ["KALETA_MIGRATE_URL"] = db_url
    try:
        command.downgrade(_alembic_config(), "-1")
    finally:
        os.environ.pop("KALETA_MIGRATE_URL", None)

    assert current_revision(db_url) != head

    ensure_schema_current(db_url)

    assert current_revision(db_url) == head
    safety = list(backup_dir.glob("kaleta-*.db"))
    assert len(safety) == 1
    assert safety[0].stat().st_size > 0
