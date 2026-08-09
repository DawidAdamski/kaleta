# SPDX-License-Identifier: AGPL-3.0-or-later
"""Persistent user configuration for database selection.

Stored at ~/.kaleta/config.json — survives app restarts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

_CONFIG_DIR = Path.home() / ".kaleta"
_CONFIG_FILE = _CONFIG_DIR / "config.json"
_MAX_RECENT = 5


def _read() -> dict[str, Any]:
    if _CONFIG_FILE.exists():
        try:
            return cast(dict[str, Any], json.loads(_CONFIG_FILE.read_text(encoding="utf-8")))
        except Exception:
            return {}
    return {}


def _write(data: dict[str, Any]) -> None:
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _CONFIG_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def get_db_url() -> str | None:
    """Return the configured database URL, or None if not yet set up."""
    return _read().get("db_url") or None


def save_db(db_url: str, name: str = "") -> None:
    """Persist the chosen database URL and update the recent list."""
    data = _read()
    data["db_url"] = db_url
    data["name"] = name

    recent: list[dict[str, str]] = data.get("recent", [])
    # deduplicate by URL
    recent = [r for r in recent if r.get("url") != db_url]
    recent.insert(0, {"url": db_url, "name": name or db_url})
    data["recent"] = recent[:_MAX_RECENT]
    _write(data)


def get_recent() -> list[dict[str, str]]:
    """Return recent database entries: [{url, name}, ...]."""
    return cast(list[dict[str, str]], _read().get("recent", []))


def is_configured() -> bool:
    """True if a database has already been chosen by the user."""
    return bool(get_db_url())


def recommended_db_path() -> Path:
    """Default on-disk SQLite path for the one-click first-run fast path."""
    return _CONFIG_DIR / "kaleta.db"


def recommended_db_url() -> str:
    """``sqlite+aiosqlite`` URL for :func:`recommended_db_path`."""
    return f"sqlite+aiosqlite:///{recommended_db_path()}"


def clear_db() -> None:
    """Remove the active database URL from config (triggers setup on next page load)."""
    data = _read()
    data.pop("db_url", None)
    data.pop("name", None)
    _write(data)


def get_nbp_fetch_on_startup() -> bool:
    """Return whether NBP Table A rates should be fetched when the process starts."""
    return bool(_read().get("nbp_fetch_on_startup", False))


def set_nbp_fetch_on_startup(enabled: bool) -> None:
    """Persist the opt-in NBP fetch-on-startup flag (default remains OFF when unset)."""
    data = _read()
    data["nbp_fetch_on_startup"] = bool(enabled)
    _write(data)
