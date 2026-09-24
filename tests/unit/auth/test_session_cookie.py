# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for the session cookie's SessionMiddleware kwargs."""

from __future__ import annotations

import logging

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from kaleta.auth.session import (
    SESSION_COOKIE_NAME,
    session_middleware_kwargs,
    warn_secure_cookie_in_debug,
)
from kaleta.config.settings import Settings


def _settings(**overrides: object) -> Settings:
    return Settings.model_validate({"debug": True, **overrides})


class TestSessionMiddlewareKwargs:
    def test_defaults_keep_local_use_unchanged(self) -> None:
        kwargs = session_middleware_kwargs(_settings())
        assert kwargs == {
            "session_cookie": "kaleta_session",
            "same_site": "lax",
            "https_only": False,
            "max_age": 259200,
        }

    def test_cookie_name_is_kaleta_session(self) -> None:
        assert SESSION_COOKIE_NAME == "kaleta_session"
        assert session_middleware_kwargs(_settings())["session_cookie"] == "kaleta_session"

    def test_secure_flag_sets_https_only(self) -> None:
        kwargs = session_middleware_kwargs(_settings(session_cookie_secure=True))
        assert kwargs["https_only"] is True

    def test_strict_samesite_is_forwarded(self) -> None:
        kwargs = session_middleware_kwargs(_settings(session_cookie_samesite="strict"))
        assert kwargs["same_site"] == "strict"

    @pytest.mark.parametrize(("ttl_hours", "max_age"), [(1, 3600), (72, 259200), (720, 2592000)])
    def test_max_age_follows_ttl(self, ttl_hours: int, max_age: int) -> None:
        kwargs = session_middleware_kwargs(_settings(session_ttl_hours=ttl_hours))
        assert kwargs["max_age"] == max_age

    def test_ttl_off_leaves_starlette_default(self) -> None:
        kwargs = session_middleware_kwargs(_settings(session_ttl_hours=0))
        assert "max_age" not in kwargs

    def test_falls_back_to_global_settings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from kaleta.auth import session as session_mod

        monkeypatch.setattr(session_mod.settings, "session_ttl_hours", 2)
        monkeypatch.setattr(session_mod.settings, "session_cookie_secure", True)
        kwargs = session_middleware_kwargs()
        assert kwargs["max_age"] == 7200
        assert kwargs["https_only"] is True


class TestSetCookieHeader:
    """The kwargs, fed to the real middleware, produce the header we promise."""

    @staticmethod
    async def _set_cookie(cfg: Settings) -> str:
        async def touch(request: Request) -> PlainTextResponse:
            request.session["id"] = "x"
            return PlainTextResponse("ok")

        app = Starlette(routes=[Route("/login", touch)])
        app.add_middleware(SessionMiddleware, secret_key="k" * 32, **session_middleware_kwargs(cfg))
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="https://test") as client:
            response = await client.get("/login")
        return response.headers["set-cookie"]

    async def test_secure_cookie_header(self) -> None:
        """Covers: KAL-AUTH-025"""
        header = (await self._set_cookie(_settings(session_cookie_secure=True))).lower()
        assert header.startswith("kaleta_session=")
        assert "; secure" in header
        assert "; httponly" in header
        assert "samesite=lax" in header
        assert "max-age=259200" in header

    async def test_default_cookie_header_is_not_secure(self) -> None:
        header = (await self._set_cookie(_settings())).lower()
        assert "; secure" not in header
        assert "httponly" in header


class TestSecureCookieDebugWarning:
    def test_warns_when_secure_and_debug(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING, logger="kaleta.auth.session"):
            warn_secure_cookie_in_debug(_settings(session_cookie_secure=True))
        assert "KALETA_SESSION_COOKIE_SECURE" in caplog.text

    @pytest.mark.parametrize(
        "overrides",
        [
            {"session_cookie_secure": False},
            {"session_cookie_secure": True, "debug": False, "secret_key": "s" * 32},
        ],
    )
    def test_silent_otherwise(
        self, caplog: pytest.LogCaptureFixture, overrides: dict[str, object]
    ) -> None:
        with caplog.at_level(logging.WARNING, logger="kaleta.auth.session"):
            warn_secure_cookie_in_debug(_settings(**overrides))
        assert caplog.text == ""
