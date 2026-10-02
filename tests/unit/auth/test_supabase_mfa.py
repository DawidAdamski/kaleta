# SPDX-License-Identifier: AGPL-3.0-or-later
"""Two-factor authentication on the hosted instance: Supabase Auth holds the factor.

Here: ``SupabaseAuthProvider`` against recorded GoTrue v2 shapes
(``httpx.MockTransport``) — which endpoint, which token, what comes back — and
the in-memory store the code prompt parks the provider's ``aal1`` session in.
``HostedMfaService`` and ``SignInFlow`` on a real database are in
``tests/integration/test_hosted_mfa.py``.

Covers: KAL-AUTH-036, KAL-AUTH-037, KAL-AUTH-038, KAL-AUTH-039
"""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from kaleta.auth import session as session_mod
from kaleta.auth.providers import (
    FactorEnrolment,
    Identity,
    LocalAuthProvider,
    MfaRequired,
    SupabaseAuthProvider,
)
from kaleta.exceptions import (
    ConflictError,
    ExternalServiceError,
    UnauthorizedError,
    ValidationError,
)

URL = "https://project.supabase.co"
ANON = "anon-key-123"
SERVICE = "service-role-key-456"
SUBJECT = "4a1c2e9b-7d3f-4b2a-9c1e-5f6a7b8c9d0e"
EMAIL = "ania@example.com"
FACTOR = "9f1e2d3c-4b5a-6978-8a9b-0c1d2e3f4a5b"
PASSWORD = "owner-password-1"
RIGHT_CODE = "123456"


# ── GoTrue shapes ─────────────────────────────────────────────────────────────


def _jwt(claims: dict[str, Any]) -> str:
    def _part(data: dict[str, Any]) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    return f"{_part({'alg': 'HS256', 'typ': 'JWT'})}.{_part(claims)}.c2lnbmF0dXJl"


def _factor(status: str = "verified", factor_id: str = FACTOR) -> dict[str, Any]:
    return {
        "id": factor_id,
        "friendly_name": "Kaleta 0a1b2c3d",
        "factor_type": "totp",
        "status": status,
        "created_at": "2026-10-01T10:00:00Z",
        "updated_at": "2026-10-01T10:01:00Z",
    }


def _session(*, aal: str = "aal1", factors: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    user: dict[str, Any] = {
        "id": SUBJECT,
        "aud": "authenticated",
        "email": EMAIL,
        "email_confirmed_at": "2026-09-30T10:00:00Z",
        "app_metadata": {"provider": "email"},
    }
    if factors is not None:
        user["factors"] = factors
    return {
        "access_token": _jwt({"sub": SUBJECT, "email": EMAIL, "aal": aal}),
        "token_type": "bearer",
        "expires_in": 3600,
        "refresh_token": "r3fr3sh",
        "user": user,
    }


class _Recorder:
    def __init__(self, *answers: httpx.Response) -> None:
        self._answers = list(answers)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self._answers.pop(0)


def _provider(
    recorder: Callable[[httpx.Request], httpx.Response], *, service_role_key: str | None = SERVICE
) -> SupabaseAuthProvider:
    return SupabaseAuthProvider(
        url=URL,
        anon_key=ANON,
        service_role_key=service_role_key,
        transport=httpx.MockTransport(recorder),
    )


def _aal1() -> Identity:
    return Identity(
        subject=SUBJECT,
        email=EMAIL,
        email_verified=True,
        access_token=_jwt({"sub": SUBJECT, "email": EMAIL, "aal": "aal1"}),
    )


# ── Provider: sign-in reports the factor ──────────────────────────────────────


async def test_a_password_sign_in_with_a_verified_factor_asks_for_the_code() -> None:
    """Covers: KAL-AUTH-037"""
    rec = _Recorder(httpx.Response(200, json=_session(factors=[_factor()])))

    result = await _provider(rec).sign_in(EMAIL, PASSWORD)

    assert isinstance(result, MfaRequired)
    assert result.factor_id == FACTOR
    assert result.identity.subject == SUBJECT
    # The aal1 token stays on the identity: it is what the code is checked with.
    assert result.identity.access_token is not None


async def test_an_unverified_factor_does_not_guard_the_login() -> None:
    """Covers: KAL-AUTH-037"""
    rec = _Recorder(httpx.Response(200, json=_session(factors=[_factor(status="unverified")])))

    result = await _provider(rec).sign_in(EMAIL, PASSWORD)

    assert isinstance(result, Identity)


async def test_a_magic_link_does_not_skip_the_second_factor() -> None:
    """Covers: KAL-AUTH-037"""
    rec = _Recorder(httpx.Response(200, json=_session(factors=[_factor()])))

    result = await _provider(rec).verify_magic_link("pkce_magic123")

    assert isinstance(result, MfaRequired)
    assert result.factor_id == FACTOR


# ── Provider: enrol, verify, unenrol ──────────────────────────────────────────


async def test_enrolment_asks_gotrue_for_a_totp_factor_with_the_users_token() -> None:
    """Covers: KAL-AUTH-036"""
    rec = _Recorder(
        httpx.Response(
            200,
            json={
                "id": FACTOR,
                "type": "totp",
                "friendly_name": "Kaleta 0a1b2c3d",
                "totp": {
                    "qr_code": "data:image/svg+xml;utf-8,<svg/>",
                    "secret": "JBSWY3DPEHPK3PXP",
                    "uri": "otpauth://totp/Kaleta:ania@example.com?secret=JBSWY3DPEHPK3PXP",
                },
            },
        )
    )
    me = _aal1()

    enrolment = await _provider(rec).mfa_enrol(me)

    assert enrolment == FactorEnrolment(
        factor_id=FACTOR,
        secret="JBSWY3DPEHPK3PXP",
        uri="otpauth://totp/Kaleta:ania@example.com?secret=JBSWY3DPEHPK3PXP",
    )
    request = rec.requests[0]
    assert request.method == "POST"
    assert request.url.path == "/auth/v1/factors"
    assert request.headers["authorization"] == f"Bearer {me.access_token}"
    assert json.loads(request.content)["factor_type"] == "totp"
    # The secret is shown once and never printed.
    assert "JBSWY3DPEHPK3PXP" not in repr(enrolment)


async def test_enrolment_without_a_token_asks_to_sign_in_again() -> None:
    """Covers: KAL-AUTH-036"""
    rec = _Recorder()
    bare = Identity(subject=SUBJECT, email=EMAIL, email_verified=True)

    with pytest.raises(UnauthorizedError):
        await _provider(rec).mfa_enrol(bare)
    assert rec.requests == []


async def test_an_incomplete_factor_is_not_shown_as_a_qr_code() -> None:
    """Covers: KAL-AUTH-036"""
    rec = _Recorder(httpx.Response(200, json={"id": FACTOR, "type": "totp"}))

    with pytest.raises(ExternalServiceError):
        await _provider(rec).mfa_enrol(_aal1())


async def test_a_right_code_lifts_the_session_to_aal2() -> None:
    """Covers: KAL-AUTH-037"""
    lifted = _session(aal="aal2", factors=[_factor()])
    rec = _Recorder(
        httpx.Response(200, json={"id": "challenge-1", "type": "totp", "expires_at": 1}),
        httpx.Response(200, json=lifted),
    )
    me = _aal1()

    result = await _provider(rec).mfa_challenge_verify(me, FACTOR, RIGHT_CODE)

    assert result.subject == SUBJECT
    assert result.access_token == lifted["access_token"]
    challenge, verify = rec.requests
    assert challenge.url.path == f"/auth/v1/factors/{FACTOR}/challenge"
    assert verify.url.path == f"/auth/v1/factors/{FACTOR}/verify"
    assert json.loads(verify.content) == {"challenge_id": "challenge-1", "code": RIGHT_CODE}
    for request in rec.requests:
        assert request.headers["authorization"] == f"Bearer {me.access_token}"


async def test_a_wrong_code_is_a_validation_error() -> None:
    """Covers: KAL-AUTH-037"""
    rec = _Recorder(
        httpx.Response(200, json={"id": "challenge-1"}),
        httpx.Response(
            422,
            json={"code": 422, "error_code": "mfa_verification_failed", "msg": "Invalid TOTP code"},
        ),
    )

    with pytest.raises(ValidationError):
        await _provider(rec).mfa_challenge_verify(_aal1(), FACTOR, "000000")


async def test_a_verify_that_did_not_reach_aal2_is_not_a_second_factor() -> None:
    """Covers: KAL-AUTH-037"""
    rec = _Recorder(
        httpx.Response(200, json={"id": "challenge-1"}),
        httpx.Response(200, json=_session(aal="aal1")),
    )

    with pytest.raises(ExternalServiceError):
        await _provider(rec).mfa_challenge_verify(_aal1(), FACTOR, RIGHT_CODE)


@pytest.mark.parametrize(
    ("status", "error"),
    [(404, ConflictError), (401, UnauthorizedError), (500, ExternalServiceError)],
)
async def test_a_challenge_that_cannot_be_made_is_typed(
    status: int, error: type[Exception]
) -> None:
    """Covers: KAL-AUTH-037"""
    rec = _Recorder(httpx.Response(status, json={"msg": "nope"}))

    with pytest.raises(error):
        await _provider(rec).mfa_challenge_verify(_aal1(), FACTOR, RIGHT_CODE)


async def test_unenrol_uses_the_admin_endpoint_with_the_service_role_key() -> None:
    """Covers: KAL-AUTH-038"""
    rec = _Recorder(httpx.Response(200, json={"id": FACTOR}))

    await _provider(rec).mfa_unenrol(SUBJECT, FACTOR)

    request = rec.requests[0]
    assert request.method == "DELETE"
    assert request.url.path == f"/auth/v1/admin/users/{SUBJECT}/factors/{FACTOR}"
    assert request.headers["authorization"] == f"Bearer {SERVICE}"
    assert request.headers["apikey"] == SERVICE


async def test_unenrolling_a_factor_already_gone_is_fine() -> None:
    """Covers: KAL-AUTH-038"""
    await _provider(_Recorder(httpx.Response(404, json={}))).mfa_unenrol(SUBJECT, FACTOR)


async def test_unenrol_without_the_service_role_key_says_what_is_missing() -> None:
    """Covers: KAL-AUTH-038"""
    with pytest.raises(ValidationError, match="SERVICE_ROLE_KEY"):
        await _provider(_Recorder(), service_role_key=None).mfa_unenrol(SUBJECT, FACTOR)


async def test_the_local_provider_leaves_the_factor_to_mfa_service() -> None:
    """Covers: KAL-AUTH-036"""
    local = LocalAuthProvider()
    with pytest.raises(ValidationError):
        await local.mfa_enrol(_aal1())
    with pytest.raises(ValidationError):
        await local.mfa_challenge_verify(_aal1(), FACTOR, RIGHT_CODE)
    with pytest.raises(ValidationError):
        await local.mfa_unenrol(SUBJECT, FACTOR)


# ── The pending code prompt keeps its token out of the session store ─────────


@pytest.fixture
def bucket(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    store: dict[str, Any] = {}
    monkeypatch.setattr(session_mod.app, "storage", type("S", (), {"user": store})())
    return store


def test_a_hosted_challenge_lives_in_memory_and_ends_with_the_prompt(
    bucket: dict[str, Any],
) -> None:
    """Covers: KAL-AUTH-037"""
    pending = MfaRequired(identity=_aal1(), factor_id=FACTOR)

    session_mod.begin_hosted_mfa_challenge(pending)

    assert session_mod.hosted_mfa_pending() == pending
    assert pending.identity.access_token not in json.dumps(bucket)
    # The local prompt does not mistake it for one of its own, nor clear it.
    assert session_mod.mfa_pending_user() is None
    assert session_mod.hosted_mfa_pending() == pending

    session_mod.clear_mfa_challenge()

    assert session_mod.hosted_mfa_pending() is None
    assert bucket == {}


def test_a_restart_forgets_the_challenge(bucket: dict[str, Any]) -> None:
    """Covers: KAL-AUTH-037"""
    session_mod.begin_hosted_mfa_challenge(MfaRequired(identity=_aal1(), factor_id=FACTOR))
    ref = bucket[session_mod.SESSION_HOSTED_MFA_REF]
    session_mod.hosted_mfa_challenges.drop(ref)  # what a new process starts with

    assert session_mod.is_hosted_mfa_pending()
    assert session_mod.hosted_mfa_pending() is None
    assert not session_mod.is_hosted_mfa_pending()


def test_the_store_lets_a_challenge_age_out() -> None:
    """Covers: KAL-AUTH-037"""
    store = session_mod.HostedMfaChallenges(ttl_seconds=0)
    ref = store.put(MfaRequired(identity=_aal1(), factor_id=FACTOR))

    assert store.get(ref) is None
