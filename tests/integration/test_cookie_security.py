# SPDX-License-Identifier: AGPL-3.0-or-later
"""A production run that serves the session cookie without Secure warns (F-3).

Covers: KAL-SEC-003
"""

from __future__ import annotations

import logging

import pytest

from kaleta.auth.session import warn_insecure_cookie_in_production
from kaleta.config.settings import Settings


def _settings(**overrides: object) -> Settings:
    return Settings.model_validate({"debug": True, **overrides})


def test_warns_when_production_serves_cookie_without_secure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Debug off and the cookie not Secure: a start-up warning is logged.

    This is the F-3 fix — before it, a production-shaped run served the session
    cookie over plain http with no warning at all.

    Covers: KAL-SEC-003
    """
    cfg = _settings(debug=False, session_cookie_secure=False, secret_key="s" * 32)
    with caplog.at_level(logging.WARNING, logger="kaleta.auth.session"):
        warn_insecure_cookie_in_production(cfg)
    assert "KALETA_SESSION_COOKIE_SECURE" in caplog.text
    assert "production-shaped" in caplog.text


@pytest.mark.parametrize(
    "overrides",
    [
        # A dev run (debug on) without Secure is the documented default — silent.
        {"session_cookie_secure": False},
        # A production run with Secure on is exactly what we want — silent.
        {"session_cookie_secure": True, "debug": False, "secret_key": "s" * 32},
    ],
)
def test_silent_in_dev_or_when_secure(
    caplog: pytest.LogCaptureFixture, overrides: dict[str, object]
) -> None:
    """No warning for a dev run, or for a production run that is already Secure.

    Covers: KAL-SEC-003
    """
    with caplog.at_level(logging.WARNING, logger="kaleta.auth.session"):
        warn_insecure_cookie_in_production(_settings(**overrides))
    assert caplog.text == ""
