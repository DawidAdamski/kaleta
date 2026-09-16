# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for the dashboard layout helpers.

Covers ``_validate_layout``, ``cycle_size``, the two Customize-dialog reset
helpers, and the legacy-migration path through ``resolve_user_layout``.
"""

from __future__ import annotations

from typing import Any

from kaleta.views.dashboard import (
    _reset_layout_full_defaults,
    _reset_layout_keep_enabled,
    _validate_layout,
)
from kaleta.views.dashboard_widgets import (
    DEFAULT_WIDGETS,
    LEGACY_KPI_WIDGETS,
    WIDGETS,
    cycle_size,
    default_layout,
    migrate_legacy_kpis,
    resolve_user_layout,
    selectable_widgets,
)


def _pick_by_default_size(cols: int, rows: int, limit: int = 1) -> list[str]:
    return [wid for wid, w in WIDGETS.items() if w.default_size == (cols, rows)][:limit]


class TestValidateLayout:
    def test_clean_payload_preserves_order(self) -> None:
        picked = _pick_by_default_size(2, 1, 3)
        payload: list[dict[str, Any]] = [{"id": wid, "cols": 2, "rows": 1} for wid in picked]
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

    def test_size_not_in_allowed_falls_back_to_the_default(self) -> None:
        """A widget is not dropped over its size.

        The banded widgets outside the grid carry no layout of their own, so
        a payload naming one with a size it does not allow used to delete it
        from the stored dashboard — a card gone for a reason its owner could
        not see. The size is the layout's business; the widget is theirs.
        """
        # total_balance allows (1,1) and (2,1); (4,4) is neither.
        payload: list[dict[str, Any]] = [
            {"id": "total_balance", "cols": 4, "rows": 4},
        ]
        default = WIDGETS["total_balance"].default_size

        result = _validate_layout(payload, default_layout())

        assert result == [{"id": "total_balance", "cols": default[0], "rows": default[1]}]

    def test_duplicate_ids_collapse(self) -> None:
        payload: list[dict[str, Any]] = [
            {"id": "total_balance", "cols": 2, "rows": 1},
            {"id": "total_balance", "cols": 1, "rows": 1},
        ]

        result = _validate_layout(payload, [])

        assert len(result) == 1
        # Keeps the FIRST occurrence.
        assert result[0] == {"id": "total_balance", "cols": 2, "rows": 1}

    def test_non_int_sizes_fall_back_to_the_default(self) -> None:
        """Same rule as an out-of-range size: keep the widget, fix the size."""
        payload: list[dict[str, Any]] = [
            {"id": "total_balance", "cols": "2", "rows": 1},
            {"id": "total_balance", "cols": 2, "rows": None},
        ]
        default = WIDGETS["total_balance"].default_size

        result = _validate_layout(payload, default_layout())

        assert result == [{"id": "total_balance", "cols": default[0], "rows": default[1]}]

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
        legacy = ["top_merchants", "cashflow_chart"]

        result = resolve_user_layout(None, legacy)

        assert [e["id"] for e in result] == legacy
        assert result[0]["cols"] == 2  # top_merchants default (2,2)
        assert result[0]["rows"] == 2
        assert result[1]["cols"] == 4  # cashflow_chart default (4,2)
        assert result[1]["rows"] == 2

    def test_fresh_user_gets_default_layout(self) -> None:
        result = resolve_user_layout(None, None)

        expected = default_layout()
        assert result == expected

    def test_invalid_size_falls_back_to_default_size(self) -> None:
        stored = [{"id": "top_merchants", "cols": 99, "rows": 99}]

        result = resolve_user_layout(stored, None)

        # The entry is kept (id is valid) but its size is clamped to default.
        assert result == [{"id": "top_merchants", "cols": 2, "rows": 2}]

    def test_unknown_id_dropped(self) -> None:
        stored = [
            {"id": "does_not_exist", "cols": 2, "rows": 1},
            {"id": "top_merchants", "cols": 2, "rows": 2},
        ]

        result = resolve_user_layout(stored, None)

        assert len(result) == 1
        assert result[0]["id"] == "top_merchants"


class TestLegacyKpiMigration:
    """The seven single-figure KPI widgets fold into the two merged cards."""

    def test_seven_kpis_become_the_two_merged_cards(self) -> None:
        """Covers: KAL-DSH-004"""
        stored = [{"id": wid, "cols": 2, "rows": 1} for wid in LEGACY_KPI_WIDGETS] + [
            {"id": "cashflow_chart", "cols": 4, "rows": 2}
        ]

        result = resolve_user_layout(stored, None)

        assert [e["id"] for e in result] == ["balance_card", "month_card", "cashflow_chart"]

    def test_a_merged_card_takes_the_position_of_what_it_replaced(self) -> None:
        """Covers: KAL-DSH-004"""
        stored = [
            {"id": "cashflow_chart", "cols": 4, "rows": 2},
            {"id": "total_balance", "cols": 2, "rows": 1},
            {"id": "recent_transactions", "cols": 4, "rows": 2},
        ]

        result = resolve_user_layout(stored, None)

        assert [e["id"] for e in result] == [
            "cashflow_chart",
            "balance_card",
            "recent_transactions",
        ]

    def test_migration_is_idempotent(self) -> None:
        """Covers: KAL-DSH-004"""
        stored = [
            {"id": "total_balance", "cols": 2, "rows": 1},
            {"id": "cashflow_chart", "cols": 4, "rows": 2},
        ]

        once = resolve_user_layout(stored, None)
        twice = resolve_user_layout(once, None)

        assert once == twice
        assert [e["id"] for e in twice].count("balance_card") == 1

    def test_a_merged_card_lands_on_its_default_size(self) -> None:
        """Covers: KAL-DSH-004"""
        result = resolve_user_layout([{"id": "month_income", "cols": 1, "rows": 1}], None)

        assert result == [{"id": "month_card", "cols": 2, "rows": 2}]

    def test_a_layout_without_legacy_ids_is_untouched(self) -> None:
        """Covers: KAL-DSH-004"""
        stored = [
            {"id": "cashflow_chart", "cols": 4, "rows": 2},
            {"id": "top_merchants", "cols": 2, "rows": 2},
        ]

        assert migrate_legacy_kpis(stored) == stored

    def test_a_partial_legacy_set_only_brings_back_what_it_replaced(self) -> None:
        """Covers: KAL-DSH-004

        A user who kept only month tiles gets the month card — not the balance
        card they had removed.
        """
        stored = [
            {"id": "month_net", "cols": 2, "rows": 1},
            {"id": "savings_rate_kpi", "cols": 2, "rows": 1},
        ]

        result = resolve_user_layout(stored, None)

        assert [e["id"] for e in result] == ["month_card"]

    def test_only_the_balance_tile_brings_back_only_the_balance_card(self) -> None:
        """Covers: KAL-DSH-004"""
        result = resolve_user_layout([{"id": "total_balance", "cols": 2, "rows": 1}], None)

        assert [e["id"] for e in result] == ["balance_card"]

    def test_legacy_widgets_are_hidden_from_the_picker(self) -> None:
        """Covers: KAL-DSH-004"""
        offered = selectable_widgets()

        assert not set(offered) & set(LEGACY_KPI_WIDGETS)
        assert "balance_card" in offered
        assert "month_card" in offered

    def test_legacy_widgets_stay_renderable(self) -> None:
        """Covers: KAL-DSH-004

        Hidden from the picker, but still in WIDGETS — a stored layout naming
        one must resolve rather than crash.
        """
        for wid in LEGACY_KPI_WIDGETS:
            assert wid in WIDGETS
            assert WIDGETS[wid].legacy is True


class TestResetLayoutKeepEnabled:
    """The ``Reset layout`` button: restore sizes and order, keep the enabled set."""

    def test_keeps_disabled_widget_disabled_and_restores_size(self) -> None:
        """Covers: KAL-DSH-001"""
        # net_worth_trend toggled off, cashflow_chart resized 4x2 -> 2x2.
        layout = [e for e in default_layout() if e["id"] != "net_worth_trend"]
        for entry in layout:
            if entry["id"] == "cashflow_chart":
                entry["cols"], entry["rows"] = 2, 2

        result = _reset_layout_keep_enabled(layout)

        ids = [e["id"] for e in result]
        assert "net_worth_trend" not in ids
        cashflow = next(e for e in result if e["id"] == "cashflow_chart")
        assert (cashflow["cols"], cashflow["rows"]) == (4, 2)

    def test_restores_canonical_order_of_enabled_widgets(self) -> None:
        """Covers: KAL-DSH-001"""
        layout = [
            {"id": "cashflow_chart", "cols": 2, "rows": 2},
            {"id": "balance_card", "cols": 2, "rows": 2},
            {"id": "month_card", "cols": 2, "rows": 2},
        ]

        result = _reset_layout_keep_enabled(layout)

        assert [e["id"] for e in result] == [
            "balance_card",
            "month_card",
            "cashflow_chart",
        ]

    def test_every_widget_lands_on_its_default_size(self) -> None:
        layout = [{"id": wid, "cols": 4, "rows": 3} for wid in ("cashflow_chart", "balance_card")]

        result = _reset_layout_keep_enabled(layout)

        for entry in result:
            w = WIDGETS[entry["id"]]
            assert (entry["cols"], entry["rows"]) == w.default_size

    def test_non_default_widget_stays_enabled_after_the_canonical_block(self) -> None:
        """An opt-in extra must not be silently disabled by a *layout* reset."""
        assert "credit_utilization" not in DEFAULT_WIDGETS
        layout = [
            {"id": "credit_utilization", "cols": 4, "rows": 2},
            {"id": "balance_card", "cols": 2, "rows": 2},
        ]

        result = _reset_layout_keep_enabled(layout)

        assert [e["id"] for e in result] == ["balance_card", "credit_utilization"]
        assert result[1]["cols"] == 2  # credit_utilization default (2, 2)
        assert result[1]["rows"] == 2

    def test_unknown_and_duplicate_ids_dropped(self) -> None:
        layout = [
            {"id": "does_not_exist", "cols": 2, "rows": 1},
            {"id": "total_balance", "cols": 1, "rows": 1},
            {"id": "total_balance", "cols": 2, "rows": 1},
        ]

        result = _reset_layout_keep_enabled(layout)

        assert result == [{"id": "total_balance", "cols": 2, "rows": 1}]

    def test_empty_layout_stays_empty(self) -> None:
        # Pure transform; the read path substitutes defaults for an empty layout.
        assert _reset_layout_keep_enabled([]) == []


class TestResetLayoutFullDefaults:
    """The ``Reset widgets`` button: everything back on, canonical size and order."""

    def test_re_enables_every_default_widget(self) -> None:
        """Covers: KAL-DSH-002"""
        layout = [{"id": "total_balance", "cols": 1, "rows": 1}]

        result = _reset_layout_full_defaults()

        ids = [e["id"] for e in result]
        assert ids == [wid for wid in DEFAULT_WIDGETS if wid in WIDGETS]
        assert "net_worth_trend" in ids
        assert len(result) > len(layout)

    def test_every_widget_at_its_default_size(self) -> None:
        """Covers: KAL-DSH-002"""
        result = _reset_layout_full_defaults()

        for entry in result:
            w = WIDGETS[entry["id"]]
            assert (entry["cols"], entry["rows"]) == w.default_size
        cashflow = next(e for e in result if e["id"] == "cashflow_chart")
        assert (cashflow["cols"], cashflow["rows"]) == (4, 2)

    def test_ignores_current_state_entirely(self) -> None:
        assert _reset_layout_full_defaults() == default_layout()
