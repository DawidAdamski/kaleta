"""Unit tests for the dashboard layout helpers.

Covers ``_validate_layout`` and ``cycle_size`` plus the legacy-migration
path through ``resolve_user_layout``.
"""

from __future__ import annotations

from typing import Any

from kaleta.views.dashboard import _validate_layout
from kaleta.views.dashboard_widgets import (
    WIDGETS,
    cycle_size,
    default_layout,
    resolve_user_layout,
)


def _pick_by_default_size(cols: int, rows: int, limit: int = 1) -> list[str]:
    return [
        wid
        for wid, w in WIDGETS.items()
        if w.default_size == (cols, rows)
    ][:limit]


class TestValidateLayout:
    def test_clean_payload_preserves_order(self) -> None:
        picked = _pick_by_default_size(2, 1, 3)
        payload: list[dict[str, Any]] = [
            {"id": wid, "cols": 2, "rows": 1} for wid in picked
        ]
        stored = default_layout()

        result = _validate_layout(payload, stored)

        assert [e["id"] for e in result] == picked
        assert all(e["cols"] == 2 and e["rows"] == 1 for e in result)

    def test_unknown_ids_stripped(self) -> None:
        picked = _pick_by_default_size(2, 1, 1)
        payload: list[dict[str, Any]] = [
            {"id": picked[0], "cols": 2, "rows": 1},
            {"id": "does_not_exist", "cols": 2, "rows": 1},
        ]

        result = _validate_layout(payload, [])

        assert len(result) == 1
        assert result[0]["id"] == picked[0]

    def test_size_not_in_allowed_rejected(self) -> None:
        # total_balance allows (1,1) and (2,1); reject (4,4).
        payload: list[dict[str, Any]] = [
            {"id": "total_balance", "cols": 4, "rows": 4},
        ]
        stored = default_layout()

        result = _validate_layout(payload, stored)

        # Filtered out entirely → falls back to stored layout.
        assert result == stored

    def test_duplicate_ids_collapse(self) -> None:
        payload: list[dict[str, Any]] = [
            {"id": "total_balance", "cols": 2, "rows": 1},
            {"id": "total_balance", "cols": 1, "rows": 1},
        ]

        result = _validate_layout(payload, [])

        assert len(result) == 1
        # Keeps the FIRST occurrence.
        assert result[0] == {"id": "total_balance", "cols": 2, "rows": 1}

    def test_non_int_sizes_skipped(self) -> None:
        payload: list[dict[str, Any]] = [
            {"id": "total_balance", "cols": "2", "rows": 1},
            {"id": "total_balance", "cols": 2, "rows": None},
        ]
        stored = default_layout()

        result = _validate_layout(payload, stored)

        assert result == stored

    def test_empty_payload_falls_back_to_stored(self) -> None:
        stored = [{"id": "total_balance", "cols": 1, "rows": 1}]

        result = _validate_layout([], stored)

        assert result == stored


class TestCycleSize:
    def test_cycles_forward(self) -> None:
        allowed = ((1, 1), (2, 1))
        assert cycle_size((1, 1), allowed) == (2, 1)
        assert cycle_size((2, 1), allowed) == (1, 1)

    def test_three_size_cycle(self) -> None:
        allowed = ((2, 2), (4, 2), (4, 3))
        assert cycle_size((2, 2), allowed) == (4, 2)
        assert cycle_size((4, 2), allowed) == (4, 3)
        assert cycle_size((4, 3), allowed) == (2, 2)

    def test_unknown_current_returns_first(self) -> None:
        allowed = ((1, 1), (2, 1))
        assert cycle_size((9, 9), allowed) == (1, 1)


class TestResolveUserLayout:
    def test_legacy_migration_uses_default_sizes(self) -> None:
        # Simulate old storage: just an ordered list of ids.
        legacy = ["total_balance", "cashflow_chart"]

        result = resolve_user_layout(None, legacy)

        assert [e["id"] for e in result] == legacy
        assert result[0]["cols"] == 2  # total_balance default (2,1)
        assert result[0]["rows"] == 1
        assert result[1]["cols"] == 4  # cashflow_chart default (4,2)
        assert result[1]["rows"] == 2

    def test_fresh_user_gets_default_layout(self) -> None:
        result = resolve_user_layout(None, None)

        expected = default_layout()
        assert result == expected

    def test_invalid_size_falls_back_to_default_size(self) -> None:
        stored = [{"id": "total_balance", "cols": 99, "rows": 99}]

        result = resolve_user_layout(stored, None)

        # The entry is kept (id is valid) but its size is clamped to default.
        assert result == [{"id": "total_balance", "cols": 2, "rows": 1}]

    def test_unknown_id_dropped(self) -> None:
        stored = [
            {"id": "does_not_exist", "cols": 2, "rows": 1},
            {"id": "total_balance", "cols": 2, "rows": 1},
        ]

        result = resolve_user_layout(stored, None)

        assert len(result) == 1
        assert result[0]["id"] == "total_balance"
