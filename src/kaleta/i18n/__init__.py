from __future__ import annotations

import json
from pathlib import Path

_LOCALES_DIR = Path(__file__).parent / "locales"
_cache: dict[str, dict] = {}


def _load(lang: str) -> dict:
    if lang not in _cache:
        path = _LOCALES_DIR / f"{lang}.json"
        if not path.exists():
            path = _LOCALES_DIR / "en.json"
        with open(path, encoding="utf-8") as f:
            _cache[lang] = json.load(f)
    return _cache[lang]


def _resolve(data: dict, parts: list[str]) -> str | None:
    node: object = data
    for part in parts:
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return None
    return node if isinstance(node, str) else None


def t(key: str, **kwargs: object) -> str:
    """Return translated string for key (dot-separated). Falls back to English, then key."""
    try:
        from nicegui import app

        lang: str = app.storage.user.get("language", "en")
    except Exception:
        lang = "en"

    parts = key.split(".")
    value = _resolve(_load(lang), parts)
    if value is None and lang != "en":
        value = _resolve(_load("en"), parts)
    if value is None:
        return key
    return value.format(**kwargs) if kwargs else value


def available_languages() -> dict[str, str]:
    """Return {code: native_name} for all locale files found."""
    result: dict[str, str] = {}
    for path in sorted(_LOCALES_DIR.glob("*.json")):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            result[path.stem] = data.get("_language_name", path.stem)
        except Exception:
            pass
    return result
