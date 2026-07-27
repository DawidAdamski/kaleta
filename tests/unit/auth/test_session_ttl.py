# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for session TTL helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest

from kaleta.auth import session as session_mod


@pytest.fixture
def fake_storage(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    store: dict[str, Any] = {}
    user = MagicMock()
    user.get = store.get
    user.__setitem__ = store.__setitem__
    user.pop = store.pop
    monkeypatch.setattr(session_mod.app, "storage", MagicMock(user=user))
    # MagicMock user doesn't wire dict methods — patch storage.user to a real dict via wrapper
    monkeypatch.setattr(session_mod.app.storage, "user", store)
    return store


class TestSessionTtl:
    def test_session_expired_when_ttl_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(session_mod.settings, "session_ttl_hours", 0)
        assert session_mod.session_expired() is False

    def test_legacy_session_without_stamp_expired(
        self, fake_storage: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Covers: KAL-AUTH-009"""
        monkeypatch.setattr(session_mod.settings, "session_ttl_hours", 72)
        fake_storage[session_mod.SESSION_AUTHENTICATED] = True
        assert session_mod.session_expired() is True

    def test_fresh_login_not_expired(
        self, fake_storage: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(session_mod.settings, "session_ttl_hours", 72)
        fake_storage[session_mod.SESSION_LOGIN_AT] = datetime.now(UTC).isoformat()
        assert session_mod.session_expired() is False

    def test_old_login_expired(
        self, fake_storage: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(session_mod.settings, "session_ttl_hours", 72)
        old = datetime.now(UTC) - timedelta(hours=73)
        fake_storage[session_mod.SESSION_LOGIN_AT] = old.isoformat()
        assert session_mod.session_expired() is True
