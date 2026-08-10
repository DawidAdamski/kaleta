# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for split discoverability labels on transaction table rows."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from kaleta.views.components.transaction_table import attach_split_labels


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
