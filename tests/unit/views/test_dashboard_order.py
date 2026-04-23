"""Unit tests for the dashboard order-merge helper.

``_merge_order`` flattens per-size reorder payloads from the client back
into the single ordered list persisted in ``app.storage.user``.
"""

from __future__ import annotations

from kaleta.views.dashboard import _merge_order
from kaleta.views.dashboard_widgets import WIDGETS


def _pick_by_size(size: str, limit: int) -> list[str]:
    """Return the first ``limit`` known widget IDs of the given size."""
    return [wid for wid, w in WIDGETS.items() if w.size == size][:limit]


class TestMergeOrder:
    def test_flatten_preserves_kpi_half_full_order(self) -> None:
        kpi = _pick_by_size("kpi", 2)
        half = _pick_by_size("half", 2)
        full = _pick_by_size("full", 2)
        stored = list(reversed(kpi + half + full))
        payload = {"kpi": kpi, "half": half, "full": full}

        result = _merge_order(payload, stored)

        assert result == kpi + half + full

    def test_unknown_widget_ids_are_stripped(self) -> None:
        kpi = _pick_by_size("kpi", 1)
        payload = {"kpi": [*kpi, "does_not_exist"], "half": [], "full": []}
        stored = list(kpi)

        result = _merge_order(payload, stored)

        assert result == kpi

    def test_size_mismatch_rejected(self) -> None:
        # A full-size widget sent under the kpi key must be dropped.
        kpi = _pick_by_size("kpi", 1)
        full = _pick_by_size("full", 1)
        stored = kpi + full
        payload = {"kpi": [*kpi, *full], "half": [], "full": []}

        result = _merge_order(payload, stored)

        assert result == kpi

    def test_disabled_widgets_stay_excluded(self) -> None:
        # A widget not in `stored` (i.e. disabled in Customize) must not be
        # resurrected by a reorder payload that includes it.
        kpi = _pick_by_size("kpi", 2)
        enabled = [kpi[0]]
        payload = {"kpi": kpi, "half": [], "full": []}

        result = _merge_order(payload, enabled)

        assert result == enabled

    def test_duplicates_collapsed(self) -> None:
        kpi = _pick_by_size("kpi", 1)
        payload = {"kpi": [*kpi, *kpi], "half": [], "full": []}

        result = _merge_order(payload, kpi)

        assert result == kpi

    def test_empty_payload_falls_back_to_stored(self) -> None:
        stored = _pick_by_size("kpi", 2)
        payload: dict[str, list[str]] = {"kpi": [], "half": [], "full": []}

        result = _merge_order(payload, stored)

        # Empty → return stored unchanged so we never nuke the layout.
        assert result == stored

    def test_missing_keys_default_to_empty(self) -> None:
        kpi = _pick_by_size("kpi", 1)
        # Payload missing 'half' and 'full' entirely — helper must not crash.
        payload: dict[str, list[str]] = {"kpi": kpi}

        result = _merge_order(payload, kpi)

        assert result == kpi

    def test_non_string_entries_skipped(self) -> None:
        kpi = _pick_by_size("kpi", 1)
        payload: dict[str, list[object]] = {  # type: ignore[assignment]
            "kpi": [*kpi, 42, None],
            "half": [],
            "full": [],
        }

        result = _merge_order(payload, kpi)  # type: ignore[arg-type]

        assert result == kpi
