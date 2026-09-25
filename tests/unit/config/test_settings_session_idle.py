# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for KALETA_SESSION_IDLE_HOURS."""

from __future__ import annotations

import logging

import pytest
from pydantic import ValidationError

from kaleta.config.settings import Settings


def test_idle_default_is_12_hours() -> None:
    settings = Settings.model_validate({"debug": True})
    assert settings.session_idle_hours == 12


def test_idle_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KALETA_DEBUG", "true")
    monkeypatch.setenv("KALETA_SESSION_IDLE_HOURS", "0")
    assert Settings().session_idle_hours == 0


def test_idle_rejects_negative() -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({"debug": True, "session_idle_hours": -1})


def test_idle_longer_than_ttl_is_capped_and_logged(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="kaleta.config.settings"):
        settings = Settings.model_validate(
            {"debug": True, "session_ttl_hours": 8, "session_idle_hours": 12}
        )
    assert settings.session_idle_hours == 8
    assert "KALETA_SESSION_IDLE_HOURS=12 exceeds KALETA_SESSION_TTL_HOURS=8" in caplog.text


def test_idle_not_capped_when_ttl_disabled() -> None:
    settings = Settings.model_validate(
        {"debug": True, "session_ttl_hours": 0, "session_idle_hours": 100}
    )
    assert settings.session_idle_hours == 100
