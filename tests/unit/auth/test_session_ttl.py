# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for session TTL and idle-timeout helpers.

Covers: KAL-AUTH-009, KAL-AUTH-031, KAL-AUTH-032
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route

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
    def test_session_expired_when_ttl_disabled(
        self, fake_storage: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Storage is needed now that the idle rule reads the activity stamp.
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


def _ago(**kwargs: float) -> str:
    return (datetime.now(UTC) - timedelta(**kwargs)).isoformat()


@pytest.fixture
def idle_12_ttl_72(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(session_mod.settings, "session_ttl_hours", 72)
    monkeypatch.setattr(session_mod.settings, "session_idle_hours", 12)


@pytest.mark.usefixtures("idle_12_ttl_72")
class TestSessionIdle:
    def test_idle_session_expires_with_idle_reason(self, fake_storage: dict[str, Any]) -> None:
        """Covers: KAL-AUTH-031"""
        fake_storage[session_mod.SESSION_LOGIN_AT] = _ago(hours=13)
        fake_storage[session_mod.SESSION_LAST_SEEN_AT] = _ago(hours=13)
        assert session_mod.session_expiry_reason() == "idle"
        assert session_mod.session_expired() is True

    def test_activity_inside_window_keeps_session_past_idle_window(
        self, fake_storage: dict[str, Any]
    ) -> None:
        """Covers: KAL-AUTH-032"""
        fake_storage[session_mod.SESSION_LOGIN_AT] = _ago(hours=30)
        fake_storage[session_mod.SESSION_LAST_SEEN_AT] = _ago(hours=11)
        assert session_mod.session_expiry_reason() is None

    def test_activity_does_not_outlive_absolute_ttl(self, fake_storage: dict[str, Any]) -> None:
        """Covers: KAL-AUTH-032"""
        fake_storage[session_mod.SESSION_LOGIN_AT] = _ago(hours=73)
        fake_storage[session_mod.SESSION_LAST_SEEN_AT] = _ago(minutes=1)
        assert session_mod.session_expiry_reason() == "ttl"

    def test_idle_disabled(
        self, fake_storage: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(session_mod.settings, "session_idle_hours", 0)
        fake_storage[session_mod.SESSION_LOGIN_AT] = _ago(hours=30)
        fake_storage[session_mod.SESSION_LAST_SEEN_AT] = _ago(hours=29)
        assert session_mod.session_expiry_reason() is None

    def test_session_without_activity_stamp_is_fresh_once(
        self, fake_storage: dict[str, Any]
    ) -> None:
        fake_storage[session_mod.SESSION_LOGIN_AT] = _ago(hours=30)
        assert session_mod.session_expiry_reason() is None
        assert session_mod.SESSION_LAST_SEEN_AT in fake_storage

    def test_login_writes_activity_stamp(self, fake_storage: dict[str, Any]) -> None:
        session_mod.login_session(user_id=1, username="ania")
        assert (
            fake_storage[session_mod.SESSION_LAST_SEEN_AT]
            == fake_storage[session_mod.SESSION_LOGIN_AT]
        )

    def test_logout_drops_activity_stamp(self, fake_storage: dict[str, Any]) -> None:
        session_mod.login_session(user_id=1, username="ania")
        session_mod.logout_session()
        assert session_mod.SESSION_LAST_SEEN_AT not in fake_storage

    def test_touch_skips_a_recent_stamp(self, fake_storage: dict[str, Any]) -> None:
        recent = _ago(seconds=60)
        fake_storage[session_mod.SESSION_LAST_SEEN_AT] = recent
        session_mod.touch_session()
        assert fake_storage[session_mod.SESSION_LAST_SEEN_AT] == recent

    def test_touch_refreshes_a_stamp_older_than_the_interval(
        self, fake_storage: dict[str, Any]
    ) -> None:
        old = _ago(seconds=301)
        fake_storage[session_mod.SESSION_LAST_SEEN_AT] = old
        session_mod.touch_session()
        refreshed = datetime.fromisoformat(fake_storage[session_mod.SESSION_LAST_SEEN_AT])
        assert datetime.now(UTC) - refreshed < timedelta(seconds=5)


@pytest.fixture
def auth_middleware_client(
    fake_storage: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> httpx.AsyncClient:
    """The real ``AuthMiddleware`` class, mounted on a bare Starlette app."""
    from nicegui import app as nicegui_app

    from kaleta.auth import middleware as middleware_mod

    captured: list[type] = []

    def _capture(cls: type) -> type:
        captured.append(cls)
        return cls

    monkeypatch.setattr(nicegui_app, "add_middleware", _capture)
    monkeypatch.setattr(middleware_mod, "is_configured", lambda: True)
    middleware_mod.register_auth_middleware()

    async def _page(_: Request) -> PlainTextResponse:
        return PlainTextResponse("ok")

    inner = Starlette(routes=[Route("/transactions", _page)])
    inner.add_middleware(captured[0])
    fake_storage[session_mod.SESSION_AUTHENTICATED] = True
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=inner), base_url="http://test")


@pytest.mark.usefixtures("idle_12_ttl_72")
class TestAuthMiddlewareIdle:
    async def test_idle_session_redirects_with_idle_reason(
        self, auth_middleware_client: httpx.AsyncClient, fake_storage: dict[str, Any]
    ) -> None:
        """Covers: KAL-AUTH-031"""
        fake_storage[session_mod.SESSION_LOGIN_AT] = _ago(hours=13)
        fake_storage[session_mod.SESSION_LAST_SEEN_AT] = _ago(hours=13)

        resp = await auth_middleware_client.get("/transactions")

        assert resp.status_code == 307
        assert resp.headers["location"] == "/login?redirect_to=/transactions&reason=idle"
        assert session_mod.SESSION_AUTHENTICATED not in fake_storage

    async def test_ttl_expiry_redirects_without_idle_reason(
        self, auth_middleware_client: httpx.AsyncClient, fake_storage: dict[str, Any]
    ) -> None:
        fake_storage[session_mod.SESSION_LOGIN_AT] = _ago(hours=73)
        fake_storage[session_mod.SESSION_LAST_SEEN_AT] = _ago(minutes=1)

        resp = await auth_middleware_client.get("/transactions")

        assert resp.headers["location"] == "/login?redirect_to=/transactions"

    async def test_active_session_passes_and_is_touched(
        self, auth_middleware_client: httpx.AsyncClient, fake_storage: dict[str, Any]
    ) -> None:
        """Covers: KAL-AUTH-032"""
        fake_storage[session_mod.SESSION_LOGIN_AT] = _ago(hours=30)
        stale = _ago(hours=11)
        fake_storage[session_mod.SESSION_LAST_SEEN_AT] = stale

        resp = await auth_middleware_client.get("/transactions")

        assert resp.status_code == 200
        assert fake_storage[session_mod.SESSION_LAST_SEEN_AT] != stale


class TestApiCookieTouch:
    @pytest.mark.parametrize(("method", "touched"), [("GET", True), ("POST", False)])
    async def test_cookie_path_touches_only_when_accepted(
        self, monkeypatch: pytest.MonkeyPatch, method: str, touched: bool
    ) -> None:
        from kaleta.api import deps
        from kaleta.exceptions import UnauthorizedError

        touches: list[None] = []
        monkeypatch.setattr(deps, "user_id_from_request", lambda _request: 7)
        monkeypatch.setattr(deps, "touch_session", lambda: touches.append(None))
        request = MagicMock(method=method)

        if touched:
            assert await deps.get_current_user_id(request, None, MagicMock()) == 7
        else:
            with pytest.raises(UnauthorizedError):
                await deps.get_current_user_id(request, None, MagicMock())
        assert len(touches) == (1 if touched else 0)
