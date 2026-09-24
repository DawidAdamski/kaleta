# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for KALETA_SESSION_COOKIE_SECURE / KALETA_SESSION_COOKIE_SAMESITE."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from kaleta.config.settings import Settings


def test_cookie_defaults() -> None:
    settings = Settings.model_validate({"debug": True})
    assert settings.session_cookie_secure is False
    assert settings.session_cookie_samesite == "lax"


def test_cookie_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KALETA_DEBUG", "true")
    monkeypatch.setenv("KALETA_SESSION_COOKIE_SECURE", "true")
    monkeypatch.setenv("KALETA_SESSION_COOKIE_SAMESITE", "Strict")
    settings = Settings()
    assert settings.session_cookie_secure is True
    assert settings.session_cookie_samesite == "strict"


@pytest.mark.parametrize("value", ["none", "loose", ""])
def test_samesite_rejects_other_values(value: str) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({"debug": True, "session_cookie_samesite": value})
