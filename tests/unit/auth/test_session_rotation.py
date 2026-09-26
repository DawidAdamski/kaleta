# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for rotating the session id on login and logout.

The HTTP tests run the real rotation route behind NiceGUI's own
``RequestTrackingMiddleware`` and Starlette's ``SessionMiddleware`` against a
file-backed ``Storage``, so they also pin the NiceGUI behaviour the rotation
relies on: a NiceGUI upgrade that stops resolving ``app.storage.user`` from
``request.session["id"]`` fails here.

Covers: KAL-AUTH-026, KAL-AUTH-027
"""

from __future__ import annotations

import base64
import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from nicegui import app as nicegui_app
from nicegui.storage import RequestTrackingMiddleware, Storage
from starlette.middleware.sessions import SessionMiddleware

from kaleta.auth import session as session_mod
from kaleta.auth.routes import build_session_router
from kaleta.auth.session import SESSION_COOKIE_NAME, SESSION_ROTATE_PATH

# ── nonce bookkeeping, on a plain dict ────────────────────────────────────────


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    bucket: dict[str, Any] = {}
    monkeypatch.setattr(session_mod.app, "storage", type("S", (), {"user": bucket})())
    return bucket


class TestRotationNonce:
    def test_a_nonce_is_good_once(self, store: dict[str, Any]) -> None:
        nonce = session_mod.stamp_rotation_nonce("logout")
        assert session_mod.consume_rotation_nonce(nonce, "logout") is not None
        assert session_mod.consume_rotation_nonce(nonce, "logout") is None

    def test_a_nonce_older_than_sixty_seconds_is_refused(self, store: dict[str, Any]) -> None:
        nonce = session_mod.stamp_rotation_nonce("logout")
        stale = datetime.now(UTC) - timedelta(seconds=61)
        store[session_mod.SESSION_ROTATE_AT] = stale.isoformat()
        assert session_mod.consume_rotation_nonce(nonce, "logout") is None
        # …and it is spent, not left for a retry.
        assert session_mod.SESSION_ROTATE_NONCE not in store

    def test_a_nonce_inside_sixty_seconds_is_accepted(self, store: dict[str, Any]) -> None:
        nonce = session_mod.stamp_rotation_nonce("logout")
        recent = datetime.now(UTC) - timedelta(seconds=59)
        store[session_mod.SESSION_ROTATE_AT] = recent.isoformat()
        assert session_mod.consume_rotation_nonce(nonce, "logout") is not None

    def test_a_wrong_guess_does_not_cancel_the_real_nonce(self, store: dict[str, Any]) -> None:
        nonce = session_mod.stamp_rotation_nonce("logout")
        assert session_mod.consume_rotation_nonce("guess", "logout") is None
        assert session_mod.consume_rotation_nonce("", "logout") is None
        assert session_mod.consume_rotation_nonce(nonce, "logout") is not None

    def test_a_logout_nonce_cannot_finish_a_login(self, store: dict[str, Any]) -> None:
        nonce = session_mod.stamp_rotation_nonce("logout")
        assert session_mod.consume_rotation_nonce(nonce, "login") is None

    def test_a_login_nonce_carries_the_parked_user(self, store: dict[str, Any]) -> None:
        nonce = session_mod.stamp_rotation_nonce("login")
        store[session_mod.SESSION_ROTATE_USER_ID] = 7
        store[session_mod.SESSION_ROTATE_USERNAME] = "ania"
        store[session_mod.SESSION_ROTATE_MFA_VERIFIED] = True
        pending = session_mod.consume_rotation_nonce(nonce, "login")
        assert pending == session_mod.PendingRotation("login", 7, "ania", mfa_verified=True)

    def test_a_login_nonce_without_a_user_is_refused(self, store: dict[str, Any]) -> None:
        nonce = session_mod.stamp_rotation_nonce("login")
        assert session_mod.consume_rotation_nonce(nonce, "login") is None


# ── the route, behind NiceGUI's real storage middleware ───────────────────────


@pytest.fixture
async def client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[tuple[httpx.AsyncClient, Storage]]:
    monkeypatch.setattr(Storage, "path", tmp_path)
    storage = Storage()
    monkeypatch.setattr(nicegui_app, "storage", storage)

    test_app = FastAPI()
    test_app.include_router(build_session_router())

    @test_app.get("/prime")
    async def prime(purpose: str, mfa: bool = False) -> PlainTextResponse:
        # What `finish_login` / `finish_logout` leave behind, minus the
        # websocket navigation this bare app has no client for.
        nicegui_app.storage.user["dark_mode"] = True
        nicegui_app.storage.user["language"] = "pl"
        if purpose == "login":
            nonce = session_mod.stamp_rotation_nonce("login")
            nicegui_app.storage.user[session_mod.SESSION_ROTATE_USER_ID] = 1
            nicegui_app.storage.user[session_mod.SESSION_ROTATE_USERNAME] = "ania"
            nicegui_app.storage.user[session_mod.SESSION_ROTATE_MFA_VERIFIED] = mfa
        else:
            session_mod.logout_session()
            nonce = session_mod.stamp_rotation_nonce("logout")
        return PlainTextResponse(nonce)

    @test_app.get("/whoami")
    async def whoami(request: Request) -> JSONResponse:
        return JSONResponse({"id": request.session["id"], "user": dict(nicegui_app.storage.user)})

    test_app.add_middleware(RequestTrackingMiddleware)
    test_app.add_middleware(
        SessionMiddleware, secret_key="test-secret", session_cookie=SESSION_COOKIE_NAME
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=test_app), base_url="http://test"
    ) as http:
        yield http, storage


def _cookie_id(http: httpx.AsyncClient) -> str:
    """The storage id inside the signed session cookie.

    The raw cookie value changes on every response (it carries a signing
    timestamp), so the id it wraps is what says whether the session moved.
    """
    raw = http.cookies[SESSION_COOKIE_NAME]
    payload = raw.split(".", 1)[0]
    decoded: dict[str, str] = json.loads(base64.b64decode(payload + "=" * (-len(payload) % 4)))
    return decoded["id"]


async def _whoami(http: httpx.AsyncClient) -> dict[str, Any]:
    body: dict[str, Any] = (await http.get("/whoami")).json()
    return body


class TestNiceGuiIdResolution:
    async def test_user_storage_is_looked_up_by_the_session_id(
        self, client: tuple[httpx.AsyncClient, Storage]
    ) -> None:
        """The pin: every request resolves ``app.storage.user`` from the cookie id."""
        http, storage = client
        first = await _whoami(http)
        assert first["id"] == _cookie_id(http)
        assert first["id"] in storage._users
        assert callable(storage._create_user_storage)


class TestRotateRoute:
    async def test_login_moves_to_a_new_id_and_authenticates_only_there(
        self, client: tuple[httpx.AsyncClient, Storage]
    ) -> None:
        """Covers: KAL-AUTH-026"""
        http, storage = client
        nonce = (await http.get("/prime", params={"purpose": "login"})).text
        before = _cookie_id(http)
        assert storage._users[before].get(session_mod.SESSION_AUTHENTICATED) is None

        resp = await http.get(SESSION_ROTATE_PATH, params={"nonce": nonce, "redirect_to": "/x"})
        assert resp.status_code == 303
        assert resp.headers["location"] == "/x"

        after = _cookie_id(http)
        assert after != before
        now = (await _whoami(http))["user"]
        assert now[session_mod.SESSION_AUTHENTICATED] is True
        assert now[session_mod.SESSION_USER_ID] == 1
        assert now["dark_mode"] is True
        assert now["language"] == "pl"
        assert not any(k in now for k in session_mod._ROTATE_KEYS)
        assert session_mod.SESSION_MFA_VERIFIED_AT not in now
        # The old bucket is empty, not merely unauthenticated.
        assert dict(storage._users[before]) == {}

    async def test_login_after_the_code_keeps_the_step_up_stamp(
        self, client: tuple[httpx.AsyncClient, Storage]
    ) -> None:
        http, _ = client
        nonce = (await http.get("/prime", params={"purpose": "login", "mfa": True})).text
        await http.get(SESSION_ROTATE_PATH, params={"nonce": nonce})
        assert session_mod.SESSION_MFA_VERIFIED_AT in (await _whoami(http))["user"]

    async def test_logout_moves_to_a_new_id_and_keeps_preferences(
        self, client: tuple[httpx.AsyncClient, Storage]
    ) -> None:
        """Covers: KAL-AUTH-027"""
        http, storage = client
        nonce = (await http.get("/prime", params={"purpose": "login"})).text
        await http.get(SESSION_ROTATE_PATH, params={"nonce": nonce})
        signed_in = _cookie_id(http)

        nonce = (await http.get("/prime", params={"purpose": "logout"})).text
        resp = await http.get(SESSION_ROTATE_PATH, params={"nonce": nonce, "logout": 1})
        assert resp.status_code == 303
        assert resp.headers["location"] == "/login"

        assert _cookie_id(http) != signed_in
        now = (await _whoami(http))["user"]
        assert now == {"dark_mode": True, "language": "pl"}
        assert dict(storage._users[signed_in]) == {}

    async def test_without_a_valid_nonce_nothing_happens(
        self, client: tuple[httpx.AsyncClient, Storage]
    ) -> None:
        http, _ = client
        await http.get("/prime", params={"purpose": "login"})
        before = _cookie_id(http)

        resp = await http.get(SESSION_ROTATE_PATH, params={"nonce": "forged"})
        assert resp.status_code == 303
        assert resp.headers["location"] == "/login"
        assert _cookie_id(http) == before
        now = (await _whoami(http))["user"]
        assert session_mod.SESSION_AUTHENTICATED not in now
        assert session_mod.SESSION_ROTATE_NONCE in now

    async def test_an_offsite_redirect_is_not_followed(
        self, client: tuple[httpx.AsyncClient, Storage]
    ) -> None:
        http, _ = client
        nonce = (await http.get("/prime", params={"purpose": "login"})).text
        resp = await http.get(
            SESSION_ROTATE_PATH, params={"nonce": nonce, "redirect_to": "//evil.example"}
        )
        assert resp.headers["location"] == "/"
