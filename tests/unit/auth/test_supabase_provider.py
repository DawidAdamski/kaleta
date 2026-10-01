# SPDX-License-Identifier: AGPL-3.0-or-later
"""SupabaseAuthProvider against recorded GoTrue responses (httpx.MockTransport).

The bodies below are GoTrue v2's shapes, trimmed to the fields Kaleta reads
plus a few it must ignore. No request leaves the process.

Covers: KAL-TEN-001
"""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from kaleta.auth.providers import Identity, SupabaseAuthProvider
from kaleta.exceptions import (
    EmailNotVerifiedError,
    ExternalServiceError,
    UnauthorizedError,
    ValidationError,
)

URL = "https://project.supabase.co"
ANON = "anon-key-123"
SERVICE = "service-role-key-456"
SUBJECT = "4a1c2e9b-7d3f-4b2a-9c1e-5f6a7b8c9d0e"
EMAIL = "ania@example.com"


def _jwt(claims: dict[str, Any]) -> str:
    def _part(data: dict[str, Any]) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    return f"{_part({'alg': 'HS256', 'typ': 'JWT'})}.{_part(claims)}.c2lnbmF0dXJl"


def _user(*, confirmed: bool = True, email: str = EMAIL, subject: str = SUBJECT) -> dict[str, Any]:
    return {
        "id": subject,
        "aud": "authenticated",
        "role": "authenticated",
        "email": email,
        "email_confirmed_at": "2026-09-30T10:00:00.000000Z" if confirmed else None,
        "phone": "",
        "app_metadata": {"provider": "email", "providers": ["email"]},
        "user_metadata": {},
        "identities": [],
        "created_at": "2026-09-30T09:59:00.000000Z",
    }


def _session(*, claims: dict[str, Any] | None = None, **user: Any) -> dict[str, Any]:
    token_claims = claims or {"sub": SUBJECT, "email": EMAIL, "aud": "authenticated", "aal": "aal1"}
    return {
        "access_token": _jwt(token_claims),
        "token_type": "bearer",
        "expires_in": 3600,
        "expires_at": 1790000000,
        "refresh_token": "r3fr3sh",
        "user": _user(**user),
    }


class _Recorder:
    """A MockTransport handler that replays one canned answer per call."""

    def __init__(self, *answers: httpx.Response) -> None:
        self._answers = list(answers)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self._answers.pop(0)


def _provider(
    recorder: Callable[[httpx.Request], httpx.Response], **kw: Any
) -> SupabaseAuthProvider:
    return SupabaseAuthProvider(
        url=URL,
        anon_key=ANON,
        service_role_key=kw.pop("service_role_key", SERVICE),
        public_url=kw.pop("public_url", "https://kaleta.example"),
        transport=httpx.MockTransport(recorder),
    )


# ── sign_in ───────────────────────────────────────────────────────────────────


async def test_sign_in_returns_the_verified_identity() -> None:
    rec = _Recorder(httpx.Response(200, json=_session()))
    identity = await _provider(rec).sign_in(" Ania@Example.com ", "hunter22")

    assert isinstance(identity, Identity)
    assert (identity.subject, identity.email, identity.email_verified) == (SUBJECT, EMAIL, True)
    assert identity.access_token is not None
    request = rec.requests[0]
    assert request.method == "POST"
    assert request.url.path == "/auth/v1/token"
    assert request.url.params["grant_type"] == "password"
    assert request.headers["apikey"] == ANON
    assert json.loads(request.content) == {"email": "Ania@Example.com", "password": "hunter22"}


async def test_the_access_token_never_shows_in_the_identity_repr() -> None:
    rec = _Recorder(httpx.Response(200, json=_session()))
    identity = await _provider(rec).sign_in(EMAIL, "hunter22")
    assert identity.access_token is not None
    assert identity.access_token not in repr(identity)
    assert "access_token" not in identity.model_dump()


async def test_wrong_credentials_are_unauthorized() -> None:
    body = {"code": 400, "error_code": "invalid_credentials", "msg": "Invalid login credentials"}
    rec = _Recorder(httpx.Response(400, json=body))
    with pytest.raises(UnauthorizedError) as exc:
        await _provider(rec).sign_in(EMAIL, "wrong")
    assert not isinstance(exc.value, EmailNotVerifiedError)


async def test_an_unconfirmed_email_is_its_own_error() -> None:
    body = {"code": 400, "error_code": "email_not_confirmed", "msg": "Email not confirmed"}
    rec = _Recorder(httpx.Response(400, json=body))
    with pytest.raises(EmailNotVerifiedError):
        await _provider(rec).sign_in(EMAIL, "hunter22")


async def test_a_token_for_someone_else_is_rejected() -> None:
    other = {"sub": "ffffffff-0000-4000-8000-000000000000", "email": EMAIL}
    rec = _Recorder(httpx.Response(200, json=_session(claims=other)))
    with pytest.raises(ExternalServiceError, match="someone else"):
        await _provider(rec).sign_in(EMAIL, "hunter22")


async def test_a_token_whose_email_claim_differs_is_rejected() -> None:
    claims = {"sub": SUBJECT, "email": "mallory@example.com"}
    rec = _Recorder(httpx.Response(200, json=_session(claims=claims)))
    with pytest.raises(ExternalServiceError, match="someone else"):
        await _provider(rec).sign_in(EMAIL, "hunter22")


async def test_a_malformed_token_is_rejected() -> None:
    session = _session()
    session["access_token"] = "not-a-jwt"
    rec = _Recorder(httpx.Response(200, json=session))
    with pytest.raises(ExternalServiceError, match="malformed"):
        await _provider(rec).sign_in(EMAIL, "hunter22")


async def test_an_unreachable_service_is_an_external_service_error() -> None:
    def _down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(ExternalServiceError, match="unreachable"):
        await _provider(_down).sign_in(EMAIL, "hunter22")


async def test_a_server_error_is_an_external_service_error() -> None:
    rec = _Recorder(httpx.Response(502, text="Bad Gateway"))
    with pytest.raises(ExternalServiceError):
        await _provider(rec).sign_in(EMAIL, "hunter22")


# ── sign_up ───────────────────────────────────────────────────────────────────


async def test_sign_up_with_confirmation_on_asks_to_check_the_inbox() -> None:
    rec = _Recorder(httpx.Response(200, json=_user(confirmed=False)))
    result = await _provider(rec).sign_up(EMAIL, "hunter22")

    assert result.identity is None
    assert result.needs_verification is True
    request = rec.requests[0]
    assert request.url.path == "/auth/v1/signup"
    assert request.url.params["redirect_to"] == "https://kaleta.example/login?reason=verified"


async def test_sign_up_with_autoconfirm_returns_an_identity() -> None:
    rec = _Recorder(httpx.Response(200, json=_session()))
    result = await _provider(rec).sign_up(EMAIL, "hunter22")
    assert result.needs_verification is False
    assert result.identity is not None
    assert result.identity.subject == SUBJECT


async def test_sign_up_for_an_existing_address_looks_like_any_other() -> None:
    body = {"code": 422, "error_code": "user_already_exists", "msg": "User already registered"}
    rec = _Recorder(httpx.Response(422, json=body))
    result = await _provider(rec).sign_up(EMAIL, "hunter22")
    assert (result.identity, result.needs_verification) == (None, True)


async def test_a_weak_password_is_a_validation_error_with_the_reason() -> None:
    body = {
        "code": 422,
        "error_code": "weak_password",
        "msg": "Password should be at least 10 characters.",
    }
    rec = _Recorder(httpx.Response(422, json=body))
    with pytest.raises(ValidationError, match="at least 10 characters"):
        await _provider(rec).sign_up(EMAIL, "short")


# ── password reset ────────────────────────────────────────────────────────────


async def test_password_reset_request_points_back_at_the_reset_page() -> None:
    rec = _Recorder(httpx.Response(200, json={}))
    await _provider(rec).request_password_reset(EMAIL)
    request = rec.requests[0]
    assert request.url.path == "/auth/v1/recover"
    assert request.url.params["redirect_to"] == "https://kaleta.example/reset-password"
    assert json.loads(request.content) == {"email": EMAIL}


async def test_password_reset_request_does_not_reveal_rate_limits() -> None:
    body = {"code": 429, "error_code": "over_email_send_rate_limit", "msg": "Too many"}
    rec = _Recorder(httpx.Response(429, json=body))
    await _provider(rec).request_password_reset(EMAIL)


async def test_confirming_a_reset_verifies_sets_the_password_and_signs_out() -> None:
    rec = _Recorder(
        httpx.Response(200, json=_session()),
        httpx.Response(200, json=_user()),
        httpx.Response(204),
    )
    await _provider(rec).confirm_password_reset("pkce_abc123", "new-password-1")

    verify, update, logout = rec.requests
    assert verify.url.path == "/auth/v1/verify"
    assert json.loads(verify.content) == {"type": "recovery", "token_hash": "pkce_abc123"}
    assert update.method == "PUT"
    assert update.url.path == "/auth/v1/user"
    assert update.headers["Authorization"].startswith("Bearer ")
    assert json.loads(update.content) == {"password": "new-password-1"}
    assert logout.url.path == "/auth/v1/logout"


async def test_an_expired_reset_link_is_a_validation_error() -> None:
    body = {"code": 403, "error_code": "otp_expired", "msg": "Token has expired or is invalid"}
    rec = _Recorder(httpx.Response(403, json=body))
    with pytest.raises(ValidationError, match="invalid or has expired"):
        await _provider(rec).confirm_password_reset("stale", "new-password-1")


# ── sign_out / delete_identity ────────────────────────────────────────────────


async def test_sign_out_ends_the_gotrue_session_with_its_own_token() -> None:
    rec = _Recorder(httpx.Response(200, json=_session()), httpx.Response(204))
    provider = _provider(rec)
    identity = await provider.sign_in(EMAIL, "hunter22")
    await provider.sign_out(identity)

    logout = rec.requests[1]
    assert logout.url.path == "/auth/v1/logout"
    assert logout.headers["Authorization"] == f"Bearer {identity.access_token}"


async def test_sign_out_without_a_token_does_nothing() -> None:
    rec = _Recorder()
    await _provider(rec).sign_out(Identity(subject=SUBJECT, email=EMAIL, email_verified=True))
    assert rec.requests == []


async def test_delete_identity_uses_the_service_role_key() -> None:
    rec = _Recorder(httpx.Response(200, json={}))
    await _provider(rec).delete_identity(SUBJECT)
    request = rec.requests[0]
    assert request.method == "DELETE"
    assert request.url.path == f"/auth/v1/admin/users/{SUBJECT}"
    assert request.headers["apikey"] == SERVICE
    assert request.headers["Authorization"] == f"Bearer {SERVICE}"


async def test_delete_identity_without_a_service_role_key_is_refused() -> None:
    rec = _Recorder()
    with pytest.raises(ValidationError, match="SERVICE_ROLE_KEY"):
        await _provider(rec, service_role_key=None).delete_identity(SUBJECT)
    assert rec.requests == []
