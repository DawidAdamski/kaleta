# SPDX-License-Identifier: AGPL-3.0-or-later
"""The optional tracker forwards no more than the anonymous event already holds."""

from __future__ import annotations

from typing import Any

import pytest

from kaleta.services import error_tracker


def _sentry_event() -> dict[str, Any]:
    return {
        "event_id": "abc",
        "level": "error",
        "tags": {"route": "/budgets", "kaleta_event_id": "EV1", "user_email": "ana@example.com"},
        "user": {"id": 7, "email": "ana@example.com"},
        "request": {"url": "https://kaleta.test/budgets?q=zabka", "data": {"amount": "12.34"}},
        "extra": {"description": "Biedronka zakupy"},
        "breadcrumbs": [{"message": "typed 120.00 into Amount"}],
        "exception": {
            "values": [
                {
                    "type": "ValueError",
                    "value": "bad amount for ana@example.com",
                    "stacktrace": {
                        "frames": [
                            {
                                "filename": "budget_service.py",
                                "lineno": 42,
                                "function": "realize",
                                "vars": {"description": "Biedronka zakupy"},
                            }
                        ]
                    },
                }
            ]
        },
    }


class TestScrubEvent:
    def test_user_request_and_breadcrumbs_are_dropped(self) -> None:
        scrubbed = error_tracker.scrub_event(_sentry_event())
        assert set(scrubbed) <= error_tracker.ALLOWED_KEYS
        for dropped in ("user", "request", "extra", "breadcrumbs"):
            assert dropped not in scrubbed

    def test_only_the_two_known_tags_survive(self) -> None:
        scrubbed = error_tracker.scrub_event(_sentry_event())
        assert scrubbed["tags"] == {"route": "/budgets", "kaleta_event_id": "EV1"}

    def test_frame_locals_are_dropped_and_the_value_is_redacted(self) -> None:
        scrubbed = error_tracker.scrub_event(_sentry_event())
        entry = scrubbed["exception"]["values"][0]
        assert entry["type"] == "ValueError"
        assert "ana@example.com" not in entry["value"]
        frame = entry["stacktrace"]["frames"][0]
        assert frame == {"filename": "budget_service.py", "lineno": 42, "function": "realize"}

    def test_the_release_is_always_this_build(self) -> None:
        assert error_tracker.scrub_event({"event_id": "abc"})["release"]


class TestInit:
    def test_without_a_dsn_the_tracker_stays_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(error_tracker, "tracker_dsn", lambda: None)
        assert error_tracker.init_error_tracker() is False

    def test_forwarding_without_a_dsn_does_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(error_tracker, "tracker_dsn", lambda: None)
        error_tracker.forward_exception(RuntimeError("boom"))
