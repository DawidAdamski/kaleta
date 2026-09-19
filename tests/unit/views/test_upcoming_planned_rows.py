# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for the upcoming-planned strip on the ledger.

The window arithmetic and the relative phrasing are pure, so they are pinned
here; the rows reaching the page are covered by the integration and e2e tests.
"""

from __future__ import annotations

import datetime
from types import SimpleNamespace

import pytest

from kaleta.views.components.transaction_table import attach_upcoming_labels
from kaleta.views.transactions.page import upcoming_window

TODAY = datetime.date(2026, 3, 10)


class TestUpcomingWindow:
    def test_off_opens_no_window(self) -> None:
        assert upcoming_window(0, today=TODAY, date_from=None, date_to=None) is None

    def test_seven_days_runs_from_today_to_the_seventh_day(self) -> None:
        assert upcoming_window(7, today=TODAY, date_from=None, date_to=None) == (
            datetime.date(2026, 3, 10),
            datetime.date(2026, 3, 17),
        )

    def test_thirty_days_runs_to_the_thirtieth_day(self) -> None:
        assert upcoming_window(30, today=TODAY, date_from=None, date_to=None) == (
            datetime.date(2026, 3, 10),
            datetime.date(2026, 4, 9),
        )

    def test_a_later_date_from_moves_the_start(self) -> None:
        assert upcoming_window(
            30,
            today=TODAY,
            date_from=datetime.date(2026, 3, 20),
            date_to=None,
        ) == (datetime.date(2026, 3, 20), datetime.date(2026, 4, 9))

    def test_a_date_from_in_the_past_does_not_open_the_window_backwards(self) -> None:
        assert upcoming_window(
            7,
            today=TODAY,
            date_from=datetime.date(2026, 1, 1),
            date_to=None,
        ) == (TODAY, datetime.date(2026, 3, 17))

    def test_an_earlier_date_to_clips_the_end(self) -> None:
        assert upcoming_window(
            30,
            today=TODAY,
            date_from=None,
            date_to=datetime.date(2026, 3, 12),
        ) == (TODAY, datetime.date(2026, 3, 12))

    def test_a_range_that_ends_in_the_past_opens_nothing(self) -> None:
        assert (
            upcoming_window(
                7,
                today=TODAY,
                date_from=None,
                date_to=datetime.date(2026, 2, 1),
            )
            is None
        )


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
