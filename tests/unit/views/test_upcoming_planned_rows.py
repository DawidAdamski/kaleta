# SPDX-License-Identifier: AGPL-3.0-or-later
"""The relative phrasing on an upcoming planned row.

Pure and locale-bound, so it is pinned here; the window arithmetic lives with
the service (``tests/unit/services/test_planned_transaction_service.py``) and
the rows reaching the page are covered by the integration and e2e tests.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from kaleta.views.components.transaction_table import attach_upcoming_labels


def _use_language(monkeypatch: pytest.MonkeyPatch, lang: str) -> None:
    class _UserStorage(dict):
        def get(self, key: str, default: object = None) -> object:
            return dict.get(self, key, default)

    class _FakeApp:
        storage = SimpleNamespace(user=_UserStorage(language=lang))

    monkeypatch.setattr("nicegui.app", _FakeApp(), raising=False)


class TestUpcomingLabels:
    def test_the_relative_phrase_follows_the_distance(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _use_language(monkeypatch, "en")
        rows = [
            {"is_planned": True, "days_ahead": 0},
            {"is_planned": True, "days_ahead": 1},
            {"is_planned": True, "days_ahead": 3},
            {"is_planned": True, "days_ahead": 13},
        ]
        labeled = attach_upcoming_labels(rows)
        assert [row["upcoming_label"] for row in labeled] == [
            "Today",
            "Tomorrow",
            "In 3 days",
            "In 13 days",
        ]

    def test_polish_takes_its_own_plural_forms(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _use_language(monkeypatch, "pl")
        rows = [
            {"is_planned": True, "days_ahead": 0},
            {"is_planned": True, "days_ahead": 1},
            {"is_planned": True, "days_ahead": 3},
            {"is_planned": True, "days_ahead": 13},
        ]
        labeled = attach_upcoming_labels(rows)
        assert [row["upcoming_label"] for row in labeled] == [
            "Dziś",
            "Jutro",
            "Za 3 dni",
            "Za 13 dni",
        ]

    def test_a_recorded_row_is_left_alone(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _use_language(monkeypatch, "en")
        rows = [{"type": "expense"}]
        assert "upcoming_label" not in attach_upcoming_labels(rows)[0]
