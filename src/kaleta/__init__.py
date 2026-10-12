# SPDX-License-Identifier: AGPL-3.0-or-later
"""Kaleta - Personal Budget & Finance Management Application."""

from __future__ import annotations

import os
from pathlib import Path


def _resolve_version() -> str:
    """The package version, derived from git by hatch-vcs — never hard-coded.

    Read from the installed package metadata (which carries the git-derived version
    baked in at build time); a clear sentinel when the package is not installed.
    """
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as _pkg_version

    try:
        return _pkg_version("kaleta")
    except PackageNotFoundError:
        return "0.0.0+unknown"


__version__ = _resolve_version()

# NiceGUI reads NICEGUI_STORAGE_PATH when its storage module is first imported.
# Pin under ~/.kaleta/ so session files do not accumulate in the process CWD
# (repo root). An explicit env override still wins via setdefault.
_NICEGUI_STORAGE = (Path.home() / ".kaleta" / "nicegui").resolve()
_NICEGUI_STORAGE.mkdir(mode=0o700, parents=True, exist_ok=True)
os.environ.setdefault("NICEGUI_STORAGE_PATH", str(_NICEGUI_STORAGE))
