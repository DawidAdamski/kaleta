# SPDX-License-Identifier: AGPL-3.0-or-later
"""The session revocation guards against a real database.

The UI guard (``AuthMiddleware``) and the API cookie path, each asked about a
session after something bumped the user's ``sessions_valid_from``.

Covers: KAL-AUTH-028, KAL-AUTH-030, KAL-AUTH-035
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import httpx
import pyotp
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from kaleta.auth import revocation_cache as cache_mod
from kaleta.auth import session as session_mod
from kaleta.auth.revocation_cache import revocation_cache
from kaleta.models.user import User
from kaleta.services.auth_service import AuthService
from kaleta.services.mfa_service import TOTP_INTERVAL, MfaService
from tests.conftest import SUITE_EMAIL, SUITE_FAMILY, SUITE_SUBJECT

REVOKED = "/login?redirect_to=/transactions&reason=signed_out_everywhere"


_FAMILY = session_mod.SessionTenant(
    tenant_id=SUITE_FAMILY.tenant_id,
    schema=SUITE_FAMILY.schema,
    auth_subject=SUITE_SUBJECT,
    email=SUITE_EMAIL,
)


def _ago(**kwargs: float) -> str:
    return (datetime.now(UTC) - timedelta(**kwargs)).isoformat()


@pytest.fixture(autouse=True)
def _empty_cache() -> Iterator[None]:
    revocation_cache.clear()
    yield
    revocation_cache.clear()


@pytest.fixture(autouse=True)
def _limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(session_mod.settings, "session_ttl_hours", 72)
    monkeypatch.setattr(session_mod.settings, "session_idle_hours", 12)


@pytest.fixture(autouse=True)
def _cache_reads_test_db(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    async def _with_session(fn: Callable[[AsyncSession], Awaitable[Any]]) -> Any:
        return await fn(session)

    monkeypatch.setattr(cache_mod, "with_session", _with_session)


class Browsers:
    """Session buckets for several browsers; ``use`` makes one the current one."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._monkeypatch = monkeypatch
        self.buckets: dict[str, dict[str, Any]] = {}

    def use(self, name: str) -> dict[str, Any]:
        bucket = self.buckets.setdefault(name, {})
        self._monkeypatch.setattr(session_mod.app, "storage", MagicMock(user=bucket))
        return bucket

    def sign_in(self, name: str, user: User, *, minutes_ago: float = 10) -> dict[str, Any]:
        bucket = self.use(name)
        session_mod.login_session(user_id=user.id, username=user.username, tenant=_FAMILY)
        bucket[session_mod.SESSION_LOGIN_AT] = _ago(minutes=minutes_ago)
        return bucket


@pytest.fixture
def browsers(monkeypatch: pytest.MonkeyPatch) -> Browsers:
    return Browsers(monkeypatch)


@pytest.fixture
def user(suite_owner: User) -> User:
    return suite_owner


@pytest.fixture
def ui(monkeypatch: pytest.MonkeyPatch) -> httpx.AsyncClient:
    """The real ``AuthMiddleware`` class, mounted on a bare Starlette app."""
    from nicegui import app as nicegui_app

    from kaleta.auth import middleware as middleware_mod

    captured: list[type] = []

    def _capture(cls: type) -> type:
        captured.append(cls)
        return cls

    monkeypatch.setattr(nicegui_app, "add_middleware", _capture)
    middleware_mod.register_auth_middleware()

    async def _page(_: Request) -> PlainTextResponse:
        return PlainTextResponse("ok")

    inner = Starlette(routes=[Route("/transactions", _page)])
    inner.add_middleware(captured[0])
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=inner), base_url="http://test")


async def test_page_load_after_reset_password_goes_to_login_with_reason(
    session: AsyncSession, user: User, browsers: Browsers, ui: httpx.AsyncClient
) -> None:
    """Covers: KAL-AUTH-028"""
    before = browsers.sign_in("laptop", user)

    # What `kaleta-admin reset-password` does in the member's family.
    await AuthService(session).revoke_sessions(user.id)

    resp = await ui.get("/transactions")
    assert resp.status_code == 307
    assert resp.headers["location"] == REVOKED
    assert session_mod.SESSION_AUTHENTICATED not in before

    # A browser that signs in after the reset is let in.
    browsers.sign_in("laptop", user, minutes_ago=0)
    assert (await ui.get("/transactions")).status_code == 200


async def test_api_cookie_path_refuses_a_revoked_session(
    session: AsyncSession,
    user: User,
    browsers: Browsers,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers: KAL-AUTH-030"""
    from kaleta.api import deps
    from kaleta.exceptions import UnauthorizedError

    monkeypatch.setattr("nicegui.storage.request_contextvar", MagicMock())
    bucket = browsers.sign_in("phone", user)
    request = MagicMock(method="GET")
    assert await deps.get_current_user_id(request, None, session) == user.id

    browsers.sign_in("laptop", user, minutes_ago=0)
    await AuthService(session).revoke_sessions(user.id)
    revocation_cache.forget(user.id)
    browsers.use("phone")

    with pytest.raises(UnauthorizedError):
        await deps.get_current_user_id(request, None, session)
    # Left for the page guard to end, so the next page load can say why.
    assert bucket[session_mod.SESSION_AUTHENTICATED] is True


async def test_changing_the_second_factor_keeps_only_the_browser_that_did_it(
    session: AsyncSession, user: User, browsers: Browsers, ui: httpx.AsyncClient
) -> None:
    """Covers: KAL-AUTH-035"""
    browsers.sign_in("phone", user)
    browsers.sign_in("laptop", user)
    # Both pages open, and the watermark (none yet) is now cached.
    assert (await ui.get("/transactions")).status_code == 200

    # The laptop turns two-factor on, then does what the Settings view does.
    mfa = MfaService(session)
    enrolment = await mfa.begin_enrolment(user.id)
    code = pyotp.TOTP(enrolment.secret, interval=TOTP_INTERVAL).at(int(time.time()))
    await mfa.confirm_enrolment(user.id, str(code))
    session_mod.keep_session_after_revocation(user.id)

    assert (await ui.get("/transactions")).status_code == 200
    browsers.use("phone")
    resp = await ui.get("/transactions")
    assert resp.headers["location"] == REVOKED
