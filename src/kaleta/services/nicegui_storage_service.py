# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pin NiceGUI file storage under ``~/.kaleta/`` and sweep stale session files.

Does not import NiceGUI (import-linter: services must not depend on views/nicegui).
``configure_environment()`` must run before ``nicegui`` is imported so
``Storage.path`` picks up ``NICEGUI_STORAGE_PATH``.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_STORAGE_DIR = Path.home() / ".kaleta" / "nicegui"
_STALE_AFTER_SECONDS = 30 * 24 * 60 * 60  # 30 days
_ENV_KEY = "NICEGUI_STORAGE_PATH"


class NiceguiStorageService:
    """Filesystem helpers for NiceGUI's local persistent storage directory."""

    def __init__(
        self,
        storage_dir: Path | None = None,
        *,
        stale_after_seconds: int = _STALE_AFTER_SECONDS,
    ) -> None:
        self.storage_dir = (storage_dir or _DEFAULT_STORAGE_DIR).expanduser().resolve()
        self.stale_after_seconds = stale_after_seconds

    @classmethod
    def configure_environment(cls, storage_dir: Path | None = None) -> Path:
        """Ensure the storage directory exists and set ``NICEGUI_STORAGE_PATH``.

        Uses ``setdefault`` so an explicit env override still wins. Call before
        importing ``nicegui``.
        """
        svc = cls(storage_dir)
        os.environ.setdefault(_ENV_KEY, str(svc.storage_dir.resolve()))
        path = Path(os.environ[_ENV_KEY]).expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True)
        logger.debug("NiceGUI storage path: %s", path)
        return path

    def sweep_stale(self, *, now: float | None = None) -> int:
        """Delete regular files under the storage dir older than the retention window.

        Returns the number of files removed. Missing directories are a no-op.
        """
        root = self.storage_dir
        if not root.is_dir():
            return 0

        cutoff = (now if now is not None else time.time()) - self.stale_after_seconds
        removed = 0
        for path in root.iterdir():
            if not path.is_file():
                continue
            try:
                mtime = path.stat().st_mtime
            except OSError:
                logger.warning("Could not stat NiceGUI storage file %s", path, exc_info=True)
                continue
            if mtime >= cutoff:
                continue
            try:
                path.unlink()
            except OSError:
                logger.warning(
                    "Could not remove stale NiceGUI storage file %s", path, exc_info=True
                )
                continue
            removed += 1
            logger.info("Removed stale NiceGUI storage file %s", path)
        if removed:
            logger.info("Swept %d stale NiceGUI storage file(s) from %s", removed, root)
        return removed
