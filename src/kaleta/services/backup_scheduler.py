# SPDX-License-Identifier: AGPL-3.0-or-later
"""Asyncio background loop for scheduled SQLite file backups."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from kaleta.config import settings
from kaleta.services.scheduled_backup_service import ScheduledBackupService

logger = logging.getLogger(__name__)


class BackupScheduler:
    """Idempotent process-wide scheduler: run once, then every N hours."""

    _task: asyncio.Task[None] | None = None

    @classmethod
    def start(cls) -> None:
        """Start the backup loop if enabled and not already running."""
        if not settings.backup_enabled:
            logger.debug("Backup scheduler not started (KALETA_BACKUP_ENABLED=false)")
            return
        if cls._task is not None and not cls._task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("Backup scheduler start skipped: no running event loop")
            return
        cls._task = loop.create_task(cls._loop(), name="kaleta-backup-scheduler")
        logger.info(
            "Backup scheduler started (interval=%sh, retain=%s, dir=%s)",
            settings.backup_interval_hours,
            settings.backup_retain,
            settings.backup_dir,
        )

    @classmethod
    async def stop(cls) -> None:
        """Cancel the background task if running."""
        task = cls._task
        cls._task = None
        if task is None:
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    @classmethod
    async def _loop(cls) -> None:
        svc = ScheduledBackupService.from_settings()
        while True:
            try:
                svc.run_once()
            except Exception:
                logger.exception("Scheduled backup failed")
            await asyncio.sleep(settings.backup_interval_hours * 3600)
