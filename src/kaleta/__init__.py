# SPDX-License-Identifier: AGPL-3.0-or-later
"""Kaleta - Personal Budget & Finance Management Application."""

from __future__ import annotations

import os
from pathlib import Path

__version__ = "0.1.0"

# NiceGUI reads NICEGUI_STORAGE_PATH when its storage module is first imported.
# Pin under ~/.kaleta/ so session files do not accumulate in the process CWD
# (repo root). An explicit env override still wins via setdefault.
_NICEGUI_STORAGE = (Path.home() / ".kaleta" / "nicegui").resolve()
_NICEGUI_STORAGE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("NICEGUI_STORAGE_PATH", str(_NICEGUI_STORAGE))
