# SPDX-License-Identifier: AGPL-3.0-or-later
"""Dashboard layout persistence — order, sizing, and legacy migration."""

from __future__ import annotations

from typing import Any

from kaleta.views.dashboard_widgets.registry import DEFAULT_WIDGETS, WIDGETS


class LayoutEntry(dict[str, Any]):
    """Plain-dict view of a single layout row: ``{id, cols, rows}``.

    Using a dict (not a TypedDict or dataclass) keeps JSON round-tripping
    trivial with FastAPI bodies and app.storage.user.
    """


def default_layout() -> list[dict[str, Any]]:
    """Fresh layout: every default widget at its declared default size."""
    return [
        {"id": wid, "cols": WIDGETS[wid].default_size[0], "rows": WIDGETS[wid].default_size[1]}
        for wid in DEFAULT_WIDGETS
        if wid in WIDGETS
    ]


def resolve_user_layout(stored_layout: Any, legacy_widgets: Any = None) -> list[dict[str, Any]]:
    """Return a cleaned layout list, migrating from legacy order if needed.

    Validation rules per entry:
    - ``id`` must exist in ``WIDGETS``
    - ``(cols, rows)`` must be in the widget's ``allowed_sizes`` —
      otherwise fall back to ``default_size``
    - Duplicates (same id seen twice) collapsed to the first occurrence
    """
    if isinstance(stored_layout, list) and stored_layout:
        cleaned: list[dict[str, Any]] = []
        seen: set[str] = set()
        for entry in stored_layout:
            if not isinstance(entry, dict):
                continue
            wid = entry.get("id")
            if not isinstance(wid, str) or wid not in WIDGETS or wid in seen:
                continue
            w = WIDGETS[wid]
            cols = entry.get("cols")
            rows = entry.get("rows")
            size = (cols, rows) if isinstance(cols, int) and isinstance(rows, int) else None
            if size not in w.allowed_sizes:
                size = w.default_size
            cleaned.append({"id": wid, "cols": size[0], "rows": size[1]})
            seen.add(wid)
        if cleaned:
            return cleaned

    # Legacy migration: storage has only the id list from the previous release.
    if isinstance(legacy_widgets, list) and legacy_widgets:
        migrated: list[dict[str, Any]] = []
        seen_legacy: set[str] = set()
        for wid in legacy_widgets:
            if not isinstance(wid, str) or wid not in WIDGETS or wid in seen_legacy:
                continue
            w = WIDGETS[wid]
            migrated.append({"id": wid, "cols": w.default_size[0], "rows": w.default_size[1]})
            seen_legacy.add(wid)
        if migrated:
            return migrated

    return default_layout()


def resolve_user_widgets(stored: Any) -> list[str]:
    """Kept for backward compatibility with older callers; delegates to the new API."""
    if not isinstance(stored, list) or not stored:
        return list(DEFAULT_WIDGETS)
    cleaned = [w for w in stored if isinstance(w, str) and w in WIDGETS]
    return cleaned or list(DEFAULT_WIDGETS)
