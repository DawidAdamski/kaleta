# SPDX-License-Identifier: AGPL-3.0-or-later
"""On-disk SQLite file backups via VACUUM INTO (not the Settings ZIP format)."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from sqlalchemy.engine import make_url

from kaleta.exceptions import ValidationError

logger = logging.getLogger(__name__)

_BACKUP_GLOB = "kaleta-*.db"


class ScheduledBackupService:
    """Create and prune timestamped SQLite snapshot files under a backup directory."""

    def __init__(self, *, db_url: str, backup_dir: Path, retain: int) -> None:
        self._db_url = db_url
        self._backup_dir = backup_dir
        self._retain = retain

    @classmethod
    def from_settings(cls) -> ScheduledBackupService:
        from kaleta.config import settings

        return cls(
            db_url=settings.db_url,
            backup_dir=Path(settings.backup_dir),
            retain=settings.backup_retain,
        )

    def resolve_sqlite_path(self) -> Path | None:
        """Return the on-disk SQLite database path, or None when not applicable."""
        url = make_url(self._db_url)
        if url.get_backend_name() != "sqlite":
            return None
        database = url.database
        if not database or database == ":memory:" or database.startswith("file::memory:"):
            return None
        return Path(database)

    def list_backups(self) -> list[Path]:
        """Return existing backup files newest-first by mtime."""
        if not self._backup_dir.is_dir():
            return []
        files = [p for p in self._backup_dir.glob(_BACKUP_GLOB) if p.is_file()]
        return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)

    def create_backup(self) -> Path | None:
        """Run VACUUM INTO a timestamped file. Returns the path, or None if skipped."""
        source = self.resolve_sqlite_path()
        if source is None:
            logger.debug("Scheduled backup skipped: non-SQLite or in-memory database")
            return None
        if not source.is_file():
            raise ValidationError(f"SQLite database file not found: {source}")

        self._backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = self._backup_dir / f"kaleta-{stamp}.db"
        if target.exists():
            # Same-second collision — add a counter suffix.
            counter = 1
            while True:
                candidate = self._backup_dir / f"kaleta-{stamp}-{counter}.db"
                if not candidate.exists():
                    target = candidate
                    break
                counter += 1

        quoted = str(target).replace("'", "''")
        conn = sqlite3.connect(str(source))
        try:
            conn.execute(f"VACUUM INTO '{quoted}'")
        finally:
            conn.close()

        logger.info("Scheduled SQLite backup written to %s", target)
        return target

    def apply_retention(self) -> list[Path]:
        """Delete backup files beyond the retention count. Returns deleted paths."""
        backups = self.list_backups()
        to_delete = backups[self._retain :]
        for path in to_delete:
            path.unlink(missing_ok=True)
            logger.info("Removed old SQLite backup %s", path)
        return to_delete

    def run_once(self) -> Path | None:
        """Create one backup and apply retention. Returns the new backup path or None."""
        path = self.create_backup()
        self.apply_retention()
        return path
