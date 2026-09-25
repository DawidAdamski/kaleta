# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration coverage for login rate-limit, session TTL and idle-timeout helpers.

Covers: KAL-AUTH-008, KAL-AUTH-009, KAL-AUTH-031, KAL-AUTH-032
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest

from kaleta.auth import session as session_mod
from kaleta.auth.login_rate_limit import LoginRateLimiter


def test_login_locks_after_five_failures() -> None:
    """Covers: KAL-AUTH-008"""
    limiter = LoginRateLimiter(max_failures=5, window_seconds=900)
    now = 1000.0
    for _ in range(4):
        assert limiter.record_failure("10.0.0.1", now=now) is False
    assert limiter.record_failure("10.0.0.1", now=now) is True
    assert limiter.is_locked("10.0.0.1", now=now) is True
    assert limiter.remaining_lock_seconds("10.0.0.1", now=now) == 900


def test_session_expires_after_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    """Covers: KAL-AUTH-009"""
    store: dict[str, Any] = {}
    monkeypatch.setattr(session_mod.app, "storage", MagicMock(user=store))
    monkeypatch.setattr(session_mod.settings, "session_ttl_hours", 72)
    old = datetime.now(UTC) - timedelta(hours=73)
    store[session_mod.SESSION_LOGIN_AT] = old.isoformat()
    assert session_mod.session_expired() is True


def _idle_session(monkeypatch: pytest.MonkeyPatch, *, login_hours: int, seen_hours: int) -> None:
    store: dict[str, Any] = {}
    monkeypatch.setattr(session_mod.app, "storage", MagicMock(user=store))
    monkeypatch.setattr(session_mod.settings, "session_ttl_hours", 72)
    monkeypatch.setattr(session_mod.settings, "session_idle_hours", 12)
    now = datetime.now(UTC)
    store[session_mod.SESSION_LOGIN_AT] = (now - timedelta(hours=login_hours)).isoformat()
    store[session_mod.SESSION_LAST_SEEN_AT] = (now - timedelta(hours=seen_hours)).isoformat()


def test_session_idle_past_window_expires_as_idle(monkeypatch: pytest.MonkeyPatch) -> None:
    """Covers: KAL-AUTH-031"""
    _idle_session(monkeypatch, login_hours=13, seen_hours=13)
    assert session_mod.session_expiry_reason() == "idle"


def test_activity_keeps_session_alive_until_absolute_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers: KAL-AUTH-032"""
    _idle_session(monkeypatch, login_hours=30, seen_hours=11)
    assert session_mod.session_expired() is False

    _idle_session(monkeypatch, login_hours=73, seen_hours=0)
    assert session_mod.session_expiry_reason() == "ttl"
