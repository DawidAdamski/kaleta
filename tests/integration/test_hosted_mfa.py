# SPDX-License-Identifier: AGPL-3.0-or-later
"""Hosted two-factor authentication on a real database, against a fake GoTrue.

``HostedMfaService`` with a real ``user_mfa`` table — the recovery codes Kaleta
keeps, and what a spent one leaves behind — and ``SignInFlow`` on a
multi-tenant database: the login prompt's two answers. The provider's HTTP
side is in ``tests/unit/auth/test_supabase_mfa.py``.

Covers: KAL-AUTH-036, KAL-AUTH-037, KAL-AUTH-038, KAL-AUTH-039
"""

from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pyotp
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.auth.providers import (
    FactorEnrolment,
    Identity,
    LocalAuthProvider,
    MfaRequired,
    set_auth_provider,
)
from kaleta.auth.sign_in import MFA_REENROL_TARGET, SignInFlow
from kaleta.db import AsyncSessionFactory
from kaleta.db.tenant_context import use_tenant
from kaleta.exceptions import (
    ConflictError,
    ExternalServiceError,
    UnauthorizedError,
    ValidationError,
)
from kaleta.models.audit_log import AuditLog
from kaleta.models.user_mfa import MFA_KIND_SUPABASE, UserMfa
from kaleta.services.auth_service import AuthService
from kaleta.services.hosted_mfa_service import HostedEnrolment, HostedMfaService
from kaleta.services.mfa_service import RECOVERY_CODE_COUNT, TOTP_INTERVAL, MfaService
from kaleta.services.tenant_service import TenantService
from tests.tenancy_helpers import MetadataProvisioner, identity, multi_tenant_database

SUBJECT = "4a1c2e9b-7d3f-4b2a-9c1e-5f6a7b8c9d0e"
EMAIL = "ania@example.com"
PASSWORD = "owner-password-1"
RIGHT_CODE = "123456"


def _jwt(claims: dict[str, Any]) -> str:
    def _part(data: dict[str, Any]) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    return f"{_part({'alg': 'HS256', 'typ': 'JWT'})}.{_part(claims)}.c2lnbmF0dXJl"


def _aal1() -> Identity:
    return Identity(
        subject=SUBJECT,
        email=EMAIL,
        email_verified=True,
        access_token=_jwt({"sub": SUBJECT, "email": EMAIL, "aal": "aal1"}),
    )


# ── HostedMfaService against a fake gateway ───────────────────────────────────


class FakeGoTrue(LocalAuthProvider):
    """A gateway that holds one account's factors the way GoTrue would."""

    name = "supabase"

    def __init__(self) -> None:
        self.factors: dict[str, str] = {}  # id → "verified" | "unverified"
        self.signed_out: list[Identity] = []
        self.unenrolled: list[tuple[str, str]] = []
        #: Who a right password signs in as.
        self.me = _aal1()
        self._minted = 0

    async def sign_in(self, email: str, password: str) -> Identity | MfaRequired:
        if password != PASSWORD:
            msg = "Invalid e-mail or password."
            raise UnauthorizedError(msg)
        verified = [fid for fid, status in self.factors.items() if status == "verified"]
        if verified:
            return MfaRequired(identity=self.me, factor_id=verified[0])
        return self.me

    async def sign_out(self, identity: Identity) -> None:
        self.signed_out.append(identity)

    async def mfa_enrol(self, identity: Identity) -> FactorEnrolment:
        self._minted += 1
        factor_id = f"factor-{self._minted}"
        self.factors[factor_id] = "unverified"
        return FactorEnrolment(
            factor_id=factor_id,
            secret="JBSWY3DPEHPK3PXP",
            uri="otpauth://totp/Kaleta:ania@example.com?secret=JBSWY3DPEHPK3PXP",
        )

    async def mfa_challenge_verify(self, identity: Identity, factor_id: str, code: str) -> Identity:
        if factor_id not in self.factors:
            msg = "That second factor no longer exists."
            raise ConflictError(msg)
        if code != RIGHT_CODE:
            msg = "That code is not right."
            raise ValidationError(msg)
        self.factors[factor_id] = "verified"
        return Identity(
            subject=identity.subject,
            email=identity.email,
            email_verified=True,
            access_token=_jwt({"sub": SUBJECT, "email": EMAIL, "aal": "aal2"}),
        )

    async def mfa_unenrol(self, subject: str, factor_id: str) -> None:
        self.unenrolled.append((subject, factor_id))
        self.factors.pop(factor_id, None)


@pytest_asyncio.fixture
async def user(session: AsyncSession):
    return await AuthService(session).create_user(EMAIL, PASSWORD)


@pytest.fixture
def gotrue() -> FakeGoTrue:
    return FakeGoTrue()


@pytest.fixture
def hosted_mfa(session: AsyncSession, gotrue: FakeGoTrue) -> HostedMfaService:
    return HostedMfaService(session, gotrue)


async def _enrol(hosted_mfa: HostedMfaService, user_id: int) -> tuple[HostedEnrolment, list[str]]:
    enrolment = await hosted_mfa.begin_hosted_enrolment(user_id, email=EMAIL, password=PASSWORD)
    codes = await hosted_mfa.confirm_hosted_enrolment(user_id, enrolment, RIGHT_CODE)
    return enrolment, codes


async def _events(session: AsyncSession) -> list[str]:
    rows = (await session.execute(select(AuditLog))).scalars().all()
    return [json.loads(row.new_data or "{}").get("event", "") for row in rows]


async def test_enrolling_keeps_the_factor_at_the_provider_and_the_codes_here(
    session: AsyncSession, user, gotrue: FakeGoTrue, hosted_mfa: HostedMfaService
) -> None:
    """Covers: KAL-AUTH-036"""
    enrolment, codes = await _enrol(hosted_mfa, user.id)

    assert enrolment.qr_svg.startswith("<svg")
    assert gotrue.factors == {enrolment.factor_id: "verified"}
    assert len(codes) == RECOVERY_CODE_COUNT
    row = (await session.execute(select(UserMfa))).scalar_one()
    assert row.kind == MFA_KIND_SUPABASE
    assert row.totp_secret == enrolment.factor_id
    assert row.enabled_at is not None
    status = await hosted_mfa.status(user.id)
    assert status.enabled
    assert status.recovery_codes_remaining == RECOVERY_CODE_COUNT
    # Kaleta keeps no provider session: the one the password opened is ended.
    assert gotrue.signed_out
    assert "mfa_enabled" in await _events(session)


async def test_a_wrong_code_at_setup_turns_nothing_on(
    session: AsyncSession, user, hosted_mfa: HostedMfaService
) -> None:
    """Covers: KAL-AUTH-036"""
    enrolment = await hosted_mfa.begin_hosted_enrolment(user.id, email=EMAIL, password=PASSWORD)

    with pytest.raises(ValidationError):
        await hosted_mfa.confirm_hosted_enrolment(user.id, enrolment, "000000")

    assert (await session.execute(select(UserMfa))).scalar_one_or_none() is None
    assert not await hosted_mfa.is_enabled(user.id)


async def test_setup_needs_the_password(user, hosted_mfa: HostedMfaService) -> None:
    """Covers: KAL-AUTH-036"""
    with pytest.raises(ValidationError, match="password"):
        await hosted_mfa.begin_hosted_enrolment(user.id, email=EMAIL, password="wrong")


async def test_setup_refuses_when_the_provider_already_guards_the_login(
    user, gotrue: FakeGoTrue, hosted_mfa: HostedMfaService
) -> None:
    """Covers: KAL-AUTH-036"""
    gotrue.factors["elsewhere"] = "verified"

    with pytest.raises(ConflictError):
        await hosted_mfa.begin_hosted_enrolment(user.id, email=EMAIL, password=PASSWORD)


async def test_a_cancelled_setup_removes_the_unverified_factor(
    user, gotrue: FakeGoTrue, hosted_mfa: HostedMfaService
) -> None:
    """Covers: KAL-AUTH-036"""
    enrolment = await hosted_mfa.begin_hosted_enrolment(user.id, email=EMAIL, password=PASSWORD)

    await hosted_mfa.abandon_hosted_enrolment(enrolment)

    assert gotrue.factors == {}
    assert gotrue.unenrolled == [(SUBJECT, enrolment.factor_id)]


async def test_the_local_code_check_never_reads_a_provider_row_as_a_secret(
    session: AsyncSession, user, hosted_mfa: HostedMfaService
) -> None:
    """Covers: KAL-AUTH-036

    The row's ``totp_secret`` holds the factor id. A code computed from that
    id as if it were a base32 secret must not pass the local check.
    """
    enrolment, _ = await _enrol(hosted_mfa, user.id)
    forged_secret = base64.b32encode(enrolment.factor_id.encode()).decode().rstrip("=")
    forged = pyotp.TOTP(forged_secret, interval=TOTP_INTERVAL).now()

    assert not await MfaService(session).verify_code(user.id, forged)
    assert not await MfaService(session).verify_challenge(user.id, forged)


async def test_the_step_up_is_the_password_and_a_code_checked_by_the_provider(
    session: AsyncSession, user, hosted_mfa: HostedMfaService
) -> None:
    """Covers: KAL-AUTH-039"""
    _, codes = await _enrol(hosted_mfa, user.id)

    assert await hosted_mfa.prove(user.id, email=EMAIL, password=PASSWORD, code=RIGHT_CODE)
    assert not await hosted_mfa.prove(user.id, email=EMAIL, password="wrong", code=RIGHT_CODE)
    assert not await hosted_mfa.prove(user.id, email=EMAIL, password=PASSWORD, code="000000")
    # A recovery code is the login prompt's to spend, not a step-up's.
    assert not await hosted_mfa.prove(user.id, email=EMAIL, password=PASSWORD, code=codes[0])
    assert (await hosted_mfa.status(user.id)).recovery_codes_remaining == RECOVERY_CODE_COUNT
    events = await _events(session)
    assert events.count("mfa_step_up") == 1
    assert events.count("mfa_step_up_failure") == 3


async def test_turning_it_off_needs_both_and_removes_the_factor_at_the_provider(
    session: AsyncSession, user, gotrue: FakeGoTrue, hosted_mfa: HostedMfaService
) -> None:
    """Covers: KAL-AUTH-039"""
    enrolment, _ = await _enrol(hosted_mfa, user.id)

    with pytest.raises(ValidationError) as wrong_password:
        await hosted_mfa.disable_hosted(user.id, email=EMAIL, password="wrong", code=RIGHT_CODE)
    with pytest.raises(ValidationError) as wrong_code:
        await hosted_mfa.disable_hosted(user.id, email=EMAIL, password=PASSWORD, code="000000")
    assert wrong_password.value.message == wrong_code.value.message
    assert await hosted_mfa.is_enabled(user.id)

    await hosted_mfa.disable_hosted(user.id, email=EMAIL, password=PASSWORD, code=RIGHT_CODE)

    assert gotrue.unenrolled == [(SUBJECT, enrolment.factor_id)]
    assert gotrue.factors == {}
    assert (await session.execute(select(UserMfa))).scalar_one_or_none() is None
    assert "mfa_disabled" in await _events(session)


async def test_a_recovery_code_removes_the_factor_and_asks_for_a_new_one(
    session: AsyncSession, user, gotrue: FakeGoTrue, hosted_mfa: HostedMfaService
) -> None:
    """Covers: KAL-AUTH-038"""
    enrolment, codes = await _enrol(hosted_mfa, user.id)

    assert not await hosted_mfa.recover(
        user.id, "NOTACODE00", subject=SUBJECT, factor_id=enrolment.factor_id
    )
    assert gotrue.unenrolled == []

    assert await hosted_mfa.recover(
        user.id, codes[0], subject=SUBJECT, factor_id=enrolment.factor_id
    )

    assert gotrue.unenrolled == [(SUBJECT, enrolment.factor_id)]
    assert not await hosted_mfa.is_enabled(user.id)
    assert await hosted_mfa.reenrolment_required(user.id)
    # The remaining codes went with the factor: none of them is worth anything now.
    assert (await hosted_mfa.status(user.id)).recovery_codes_remaining == 0
    assert "mfa_recovered" in await _events(session)

    # Setting it up again clears the marker.
    await _enrol(hosted_mfa, user.id)
    assert await hosted_mfa.is_enabled(user.id)
    assert not await hosted_mfa.reenrolment_required(user.id)


async def test_a_provider_that_cannot_remove_the_factor_costs_no_code(
    user, gotrue: FakeGoTrue, hosted_mfa: HostedMfaService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Covers: KAL-AUTH-038"""
    enrolment, codes = await _enrol(hosted_mfa, user.id)

    async def _outage(subject: str, factor_id: str) -> None:
        msg = "The sign-in service is not answering properly."
        raise ExternalServiceError(msg)

    monkeypatch.setattr(gotrue, "mfa_unenrol", _outage)
    with pytest.raises(ExternalServiceError):
        await hosted_mfa.recover(user.id, codes[0], subject=SUBJECT, factor_id=enrolment.factor_id)

    assert await hosted_mfa.is_enabled(user.id)
    assert not await hosted_mfa.reenrolment_required(user.id)
    assert (await hosted_mfa.status(user.id)).recovery_codes_remaining == RECOVERY_CODE_COUNT

    monkeypatch.undo()
    assert await hosted_mfa.recover(
        user.id, codes[0], subject=SUBJECT, factor_id=enrolment.factor_id
    )


async def test_an_abandoned_local_enrolment_is_not_a_reenrolment(
    session: AsyncSession, user
) -> None:
    """Covers: KAL-AUTH-038"""
    await MfaService(session).begin_enrolment(user.id)

    assert not await MfaService(session).reenrolment_required(user.id)


# ── SignInFlow: the login prompt's two answers ────────────────────────────────


@pytest.fixture
async def tenancy(tmp_path: Path) -> AsyncIterator[tuple[str, FakeGoTrue]]:
    gotrue = FakeGoTrue()
    gotrue.me = identity(1)
    set_auth_provider(gotrue)
    try:
        async with multi_tenant_database(tmp_path) as url:
            yield url, gotrue
    finally:
        set_auth_provider(None)


async def _hosted_member(url: str, gotrue: FakeGoTrue) -> tuple[MfaRequired, list[str], int]:
    """A provisioned member with the factor on; their pending sign-in and recovery codes."""
    member = identity(1)
    async with AsyncSessionFactory.public() as public:
        service = TenantService(public, provisioner=MetadataProvisioner(url))
        membership = await service.membership_for_sign_in(member)
    user_id = membership.member.user_id
    assert user_id is not None
    with use_tenant(membership.context()):
        async with AsyncSessionFactory() as session:
            hosted = HostedMfaService(session, gotrue)
            enrolment = await hosted.begin_hosted_enrolment(
                user_id, email=member.email, password=PASSWORD
            )
            codes = await hosted.confirm_hosted_enrolment(user_id, enrolment, RIGHT_CODE)
    pending = MfaRequired(identity=member, factor_id=enrolment.factor_id)
    return pending, codes, user_id


async def test_the_right_code_completes_the_hosted_sign_in(
    tenancy: tuple[str, FakeGoTrue],
) -> None:
    """Covers: KAL-AUTH-037"""
    url, gotrue = tenancy
    pending, _, user_id = await _hosted_member(url, gotrue)

    with pytest.raises(ValidationError):
        await SignInFlow().verify_code(pending, "000000")
    signed_in = await SignInFlow().verify_code(pending, " 123 456 ")

    assert signed_in.user_id == user_id
    assert signed_in.tenant is not None
    assert not signed_in.reenrol_mfa
    assert signed_in.target("/transactions") == "/transactions"


async def test_a_recovery_code_signs_in_and_sends_the_next_sign_in_to_set_up_again(
    tenancy: tuple[str, FakeGoTrue],
) -> None:
    """Covers: KAL-AUTH-038"""
    url, gotrue = tenancy
    pending, codes, user_id = await _hosted_member(url, gotrue)

    assert await SignInFlow().recover(pending, "NOTACODE00") is None
    signed_in = await SignInFlow().recover(pending, codes[0])

    assert signed_in is not None
    assert signed_in.user_id == user_id
    assert signed_in.reenrol_mfa
    assert signed_in.target("/transactions") == MFA_REENROL_TARGET
    assert gotrue.factors == {}
    # The next sign-in has only the password to give, and still lands there.
    again = await gotrue.sign_in(pending.identity.email, PASSWORD)
    assert isinstance(again, Identity)
    assert (await SignInFlow().complete(again)).reenrol_mfa
    # The spent code cannot be used a second time.
    assert await SignInFlow().recover(pending, codes[0]) is None
