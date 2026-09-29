# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pin NiceGUI storage (files under ``~/.kaleta/`` or Redis), lock it down, sweep it.

Does not import NiceGUI (import-linter: services must not depend on views/nicegui).
``configure_environment()`` must run before ``nicegui`` is imported so
``Storage`` picks up ``NICEGUI_STORAGE_PATH`` / ``NICEGUI_REDIS_URL``.

The files are one JSON document per browser. Nothing secret goes into them
(ADR-035, guarded by ``tests/unit/auth/test_session_contents.py``), but they
still say who is signed in, so the directory is ``0o700`` and each file
``0o600``: on a host whose data volume other services share, the Unix user
that runs Kaleta is the only one that may read them.
"""

from __future__ import annotations

import logging
import os
import stat
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_STORAGE_DIR = Path.home() / ".kaleta" / "nicegui"
_STALE_AFTER_SECONDS = 30 * 24 * 60 * 60  # 30 days
_ENV_KEY = "NICEGUI_STORAGE_PATH"
_REDIS_URL_ENV_KEY = "NICEGUI_REDIS_URL"
_REDIS_PREFIX_ENV_KEY = "NICEGUI_REDIS_KEY_PREFIX"
#: NiceGUI's keys become ``kaleta:user-<id>``, ``kaleta:general``, … — beside
#: the rate limiter's ``kaleta:login:…`` rather than NiceGUI's generic prefix.
_REDIS_KEY_PREFIX = "kaleta:"
_DIR_MODE = 0o700
_FILE_MODE = 0o600


class NiceguiStorageService:
    """Filesystem helpers for NiceGUI's local persistent storage directory."""

    def __init__(
        self,
        storage_dir: Path | None = None,
        *,
        stale_after_seconds: int = _STALE_AFTER_SECONDS,
    ) -> None:
        # Without an explicit dir, the one NiceGUI actually writes to: an
        # operator's NICEGUI_STORAGE_PATH, else the ~/.kaleta default.
        default = Path(os.environ.get(_ENV_KEY) or _DEFAULT_STORAGE_DIR)
        self.storage_dir = (storage_dir or default).expanduser().resolve()
        self.stale_after_seconds = stale_after_seconds

    @classmethod
    def configure_environment(
        cls, storage_dir: Path | None = None, *, redis_url: str | None = None
    ) -> Path:
        """Ensure the storage directory exists and point NiceGUI at its storage.

        Sets ``NICEGUI_STORAGE_PATH``; with ``redis_url`` (``KALETA_REDIS_URL``)
        also ``NICEGUI_REDIS_URL`` and ``NICEGUI_REDIS_KEY_PREFIX``, which move
        ``app.storage.user`` into Redis. Uses ``setdefault`` so an explicit env
        override still wins. Call before importing ``nicegui``.
        """
        svc = cls(storage_dir)
        os.environ.setdefault(_ENV_KEY, str(svc.storage_dir.resolve()))
        path = Path(os.environ[_ENV_KEY]).expanduser().resolve()
        path.mkdir(mode=_DIR_MODE, parents=True, exist_ok=True)
        logger.debug("NiceGUI storage path: %s", path)
        if redis_url:
            os.environ.setdefault(_REDIS_URL_ENV_KEY, redis_url)
            os.environ.setdefault(_REDIS_PREFIX_ENV_KEY, _REDIS_KEY_PREFIX)
            logger.debug("NiceGUI user storage in Redis (prefix %s)", _REDIS_KEY_PREFIX)
        return path

    @staticmethod
    def restrict_new_files() -> None:
        """Make everything this process creates owner-only (umask ``077``).

        ``tighten_permissions()`` alone does not hold: NiceGUI saves a session
        by writing a temp file and renaming it over the old one, so every save
        is a new file with the process umask, and a ``0o600`` set at startup is
        gone after the first request. The umask is the one place that governs
        those writes. It also covers the database, backups and exports, which
        are no less private. Only ever narrows: an operator's stricter umask
        stays. A no-op on Windows.
        """
        if os.name == "nt":
            return
        current = os.umask(0o077)
        os.umask(current | 0o077)

    def tighten_permissions(self) -> int:
        """Make the directory ``0o700`` and every file in it ``0o600``.

        For files left by an older version or written under a looser umask;
        ``restrict_new_files()`` keeps new ones owner-only. Runs at startup
        after the sweep. Returns how many entries needed fixing and
        logs once when any did. A no-op on Windows, where modes mean little.
        """
        if os.name == "nt":
            logger.debug("Skipping NiceGUI storage permissions on Windows")
            return 0
        root = self.storage_dir
        if not root.is_dir():
            return 0

        fixed = 0
        entries = [(root, _DIR_MODE)] + [
            (path, _FILE_MODE) for path in root.iterdir() if path.is_file()
        ]
        for path, mode in entries:
            try:
                current = stat.S_IMODE(path.stat().st_mode)
                if current == mode:
                    continue
                path.chmod(mode)
            except OSError:
                logger.warning("Could not restrict permissions on %s", path, exc_info=True)
                continue
            fixed += 1
        if fixed:
            logger.info(
                "Restricted permissions on %d NiceGUI storage entr%s in %s",
                fixed,
                "y" if fixed == 1 else "ies",
                root,
            )
        return fixed

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
