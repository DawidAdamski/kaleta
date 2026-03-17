"""Persistent user configuration for database selection.

Stored at ~/.kaleta/config.json — survives app restarts.
"""
from __future__ import annotations

import json
from pathlib import Path

_CONFIG_DIR = Path.home() / ".kaleta"
_CONFIG_FILE = _CONFIG_DIR / "config.json"
_MAX_RECENT = 5


def _read() -> dict:
    if _CONFIG_FILE.exists():
        try:
            return json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _write(data: dict) -> None:
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

    recent: list[dict] = data.get("recent", [])
    # deduplicate by URL
    recent = [r for r in recent if r.get("url") != db_url]
    recent.insert(0, {"url": db_url, "name": name or db_url})
    data["recent"] = recent[:_MAX_RECENT]
    _write(data)


def get_recent() -> list[dict]:
    """Return recent database entries: [{url, name}, ...]."""
    return _read().get("recent", [])


def is_configured() -> bool:
    """True if a database has already been chosen by the user."""
    return bool(get_db_url())


def clear_db() -> None:
    """Remove the active database URL from config (triggers setup on next page load)."""
    data = _read()
    data.pop("db_url", None)
    data.pop("name", None)
    _write(data)
