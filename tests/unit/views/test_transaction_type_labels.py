# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for translated transaction type labels in table rows."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from kaleta.views.components.transaction_table import attach_type_labels


def test_attach_type_labels_uses_polish_common_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Covers: KAL-TXN-006"""

    class _UserStorage(dict):
        def get(self, key: str, default: object = None) -> object:
            return dict.get(self, key, default)

    class _FakeApp:
        storage = SimpleNamespace(user=_UserStorage(language="pl"))

    monkeypatch.setattr("nicegui.app", _FakeApp(), raising=False)

    rows = [
        {"type": "expense", "amount": "-10.00"},
        {"type": "income", "amount": "+20.00"},
        {"type": "transfer", "amount": "-5.00"},
    ]
    labeled = attach_type_labels(rows)

    assert labeled[0]["type"] == "expense"
    assert labeled[0]["type_label"] == "Wydatek"
    assert labeled[1]["type"] == "income"
    assert labeled[1]["type_label"] == "Przychód"
    assert labeled[2]["type"] == "transfer"
    assert labeled[2]["type_label"] == "Przelew"
