# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for split discoverability labels on transaction table rows."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from kaleta.views.components.transaction_table import attach_split_labels, space_amounts


def test_attach_split_labels_uses_polish_split_category(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers: KAL-SPL-005"""

    class _UserStorage(dict):
        def get(self, key: str, default: object = None) -> object:
            return dict.get(self, key, default)

    class _FakeApp:
        storage = SimpleNamespace(user=_UserStorage(language="pl"))

    monkeypatch.setattr("nicegui.app", _FakeApp(), raising=False)

    rows = [
        {"has_splits": True, "split_count": 2, "category": "Split (2)"},
        {"has_splits": False, "split_count": 0, "category": "Groceries"},
    ]
    labeled = attach_split_labels(rows)

    assert labeled[0]["category"] == "Podzielona (2)"
    assert labeled[1]["category"] == "Groceries"


def test_attach_split_labels_english_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Covers: KAL-SPL-005"""

    class _UserStorage(dict):
        def get(self, key: str, default: object = None) -> object:
            return dict.get(self, key, default)

    class _FakeApp:
        storage = SimpleNamespace(user=_UserStorage(language="en"))

    monkeypatch.setattr("nicegui.app", _FakeApp(), raising=False)

    rows = [{"has_splits": True, "split_count": 2, "category": "placeholder"}]
    labeled = attach_split_labels(rows)
    assert labeled[0]["category"] == "Split (2)"


class TestSpaceAmounts:
    """The ledger's figures are grouped the way artboard `2a` writes them.

    Covers: KAL-TXN-017 — the row's figure is the service's string, and the
    service writes Python's comma because the API reads it too. The ledger
    puts its own grouping on at the point it is drawn.
    """

    def test_a_row_figure_and_its_group_net_are_both_spaced(self) -> None:
        rows = [{"amount": "-2,400.00", "sep_net": "+9,111.26"}]

        assert space_amounts(rows) == [{"amount": "-2 400.00", "sep_net": "+9 111.26"}]

    def test_a_figure_under_a_thousand_is_left_alone(self) -> None:
        assert space_amounts([{"amount": "-49.00"}]) == [{"amount": "-49.00"}]

    def test_a_row_with_no_figures_survives(self) -> None:
        # A separator row carries a label and no net of its own until the
        # service attaches one.
        assert space_amounts([{"sep_label": "Week 39"}]) == [{"sep_label": "Week 39"}]
