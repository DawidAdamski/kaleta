# SPDX-License-Identifier: AGPL-3.0-or-later
"""Local logins on the registry layout (ADR-38, ``postgres-only`` part A).

``KALETA_TENANCY=multi`` with ``KALETA_AUTH_BACKEND=local``: logins live in
``public.local_identities``, the first one is the instance administrator, and
a sign-in provisions the login's family exactly as a Supabase sign-in does.

Covers: KAL-TEN-015, KAL-TEN-016, KAL-TEN-017, KAL-TEN-018, KAL-TEN-019, KAL-TEN-020,
KAL-TEN-021, KAL-TEN-022
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import io
import sys
import time
from collections.abc import AsyncIterator
from pathlib import Path

import pyotp
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from kaleta.api import create_api_router
from kaleta.api.errors import register_error_handlers
from kaleta.auth.local_logins import set_login_disabled
from kaleta.auth.providers import MfaRequired, RegistryAuthProvider, set_auth_provider
from kaleta.auth.sign_in import SignInFlow, registry_sign_up_state
from kaleta.auth.unlock import is_local_login_password
from kaleta.config import settings
from kaleta.db import AsyncSessionFactory
from kaleta.db.tenant_context import use_tenant
from kaleta.exceptions import ConflictError, UnauthorizedError, ValidationError
from kaleta.models.tenant import TenantMemberStatus, TenantRole
from kaleta.schemas.identity import Identity, RegistrationMode
from kaleta.services import ApiTokenService, AuthService
from kaleta.services.local_identity_service import LocalIdentityService
from kaleta.services.mfa_service import TOTP_INTERVAL, MfaService
from kaleta.services.tenant_service import TenantService
from tests.tenancy_helpers import MetadataProvisioner, multi_tenant_database

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "tenant_admin.py"
_spec = importlib.util.spec_from_file_location("tenant_admin", SCRIPT)
assert _spec is not None and _spec.loader is not None
tenant_admin = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("tenant_admin", tenant_admin)
_spec.loader.exec_module(tenant_admin)

ADMIN = "Admin@Example.com"
PASSWORD = "correct horse battery"


@pytest.fixture
async def instance(tmp_path: Path) -> AsyncIterator[str]:
    provider = RegistryAuthProvider()
    set_auth_provider(provider)
    try:
        async with multi_tenant_database(auth_backend="local") as url:
            yield url
    finally:
        set_auth_provider(None)


def _flow(url: str) -> SignInFlow:
    """SignInFlow with the fast schema builder; the registry session is its own."""

    class _Flow(SignInFlow):
        async def _membership(self, identity: Identity):  # type: ignore[no-untyped-def]
            async with AsyncSessionFactory.public() as public:
                service = TenantService(public, provisioner=MetadataProvisioner(url))
                return await service.membership_for_sign_in(identity)

    return _Flow()


async def _set_mode(mode: RegistrationMode) -> None:
    async with AsyncSessionFactory.public() as public:
        await LocalIdentityService(public).set_registration_mode(mode)


async def test_the_first_sign_up_creates_the_administrator_and_the_first_family(
    instance: str,
) -> None:
    """Covers: KAL-TEN-015"""
    assert (await registry_sign_up_state()).first_run

    result = await RegistryAuthProvider().sign_up(ADMIN, PASSWORD)
    assert result.identity is not None
    assert not result.needs_verification
    signed_in = await _flow(instance).complete(result.identity)

    async with AsyncSessionFactory.public() as public:
        row = await LocalIdentityService(public).get_by_email("admin@example.com")
        membership = await TenantService(public).get_member_by_subject(result.identity.subject)
    assert row is not None
    assert row.is_instance_admin
    assert result.identity.subject == f"local:{row.id}"
    assert membership is not None
    assert membership.member.role is TenantRole.OWNER
    assert signed_in.tenant is not None
    assert signed_in.tenant.tenant_id == membership.tenant.id
    assert signed_in.user_id == membership.member.user_id
    assert not (await registry_sign_up_state()).first_run


async def test_sign_up_follows_the_registration_mode(instance: str) -> None:
    """Covers: KAL-TEN-016"""
    await RegistryAuthProvider().sign_up(ADMIN, PASSWORD)

    state = await registry_sign_up_state()
    assert not state.open
    with pytest.raises(ValidationError, match="Sign-up is closed"):
        await RegistryAuthProvider().sign_up("guest@example.com", PASSWORD)

    await _set_mode(RegistrationMode.OPEN)
    assert (await registry_sign_up_state()).open
    result = await RegistryAuthProvider().sign_up("guest@example.com", PASSWORD)
    assert result.identity is not None
    guest = await _flow(instance).complete(result.identity)
    admin = await _flow(instance).complete(
        await RegistryAuthProvider().sign_in(ADMIN, PASSWORD)  # type: ignore[arg-type]
    )

    assert guest.tenant is not None
    assert admin.tenant is not None
    assert guest.tenant.tenant_id != admin.tenant.tenant_id
    async with AsyncSessionFactory.public() as public:
        row = await LocalIdentityService(public).get_by_email("guest@example.com")
    assert row is not None
    assert not row.is_instance_admin
    with pytest.raises(ConflictError):
        await RegistryAuthProvider().sign_up("GUEST@example.com", PASSWORD)


async def test_a_local_login_signs_in_by_e_mail_and_refuses_wrong_or_disabled(
    instance: str,
) -> None:
    """Covers: KAL-TEN-017"""
    await RegistryAuthProvider().sign_up(ADMIN, PASSWORD)
    await _set_mode(RegistrationMode.OPEN)
    await RegistryAuthProvider().sign_up("member@example.com", PASSWORD)

    identity = await RegistryAuthProvider().sign_in("  MEMBER@example.com ", PASSWORD)
    assert isinstance(identity, Identity)
    assert identity.email == "member@example.com"
    assert identity.email_verified

    with pytest.raises(UnauthorizedError, match="Invalid e-mail or password") as wrong:
        await RegistryAuthProvider().sign_in("member@example.com", "not the password")
    with pytest.raises(UnauthorizedError) as unknown:
        await RegistryAuthProvider().sign_in("nobody@example.com", PASSWORD)
    assert str(wrong.value) == str(unknown.value)

    async with AsyncSessionFactory.public() as public:
        identities = LocalIdentityService(public)
        row = await identities.get_by_email("member@example.com")
        assert row is not None
        await identities.set_disabled(row.id, True)
    with pytest.raises(UnauthorizedError, match="Invalid e-mail or password"):
        await RegistryAuthProvider().sign_in("member@example.com", PASSWORD)


async def test_the_last_administrator_is_kept(instance: str) -> None:
    """Covers: KAL-TEN-015 — an instance never loses its administrator."""
    await RegistryAuthProvider().sign_up(ADMIN, PASSWORD)
    async with AsyncSessionFactory.public() as public:
        identities = LocalIdentityService(public)
        row = await identities.get_by_email(ADMIN)
        assert row is not None
        admin_id = row.id  # a refused decision rolls back and expires `row`
        with pytest.raises(ValidationError, match="last administrator"):
            await identities.set_disabled(admin_id, True)
        with pytest.raises(ValidationError, match="last administrator"):
            await identities.delete(admin_id)


async def test_a_local_second_factor_is_checked_inside_the_family(instance: str) -> None:
    """Covers: KAL-TEN-018"""
    result = await RegistryAuthProvider().sign_up(ADMIN, PASSWORD)
    assert result.identity is not None
    signed_in = await _flow(instance).complete(result.identity)
    assert signed_in.tenant is not None
    async with AsyncSessionFactory.public() as public:
        membership = await TenantService(public).get_member_by_subject(result.identity.subject)
    assert membership is not None
    with use_tenant(membership.context()):
        async with AsyncSessionFactory() as session:
            mfa = MfaService(session)
            enrolment = await mfa.begin_enrolment(signed_in.user_id)
            totp = pyotp.TOTP(enrolment.secret, interval=TOTP_INTERVAL)
            codes = await mfa.confirm_enrolment(signed_in.user_id, totp.now())

    pending = await RegistryAuthProvider().sign_in(ADMIN, PASSWORD)
    assert isinstance(pending, MfaRequired)
    assert pending.factor_id == "local"

    with pytest.raises(ValidationError):
        await _flow(instance).verify_code(pending, "000000")
    # The enrolment spent the current step's code; the next step (inside the
    # drift window) is fresh.
    next_code = totp.at(int(time.time()) + TOTP_INTERVAL)
    verified = await _flow(instance).verify_code(pending, next_code)
    assert verified.user_id == signed_in.user_id
    with pytest.raises(ValidationError):
        await _flow(instance).verify_code(pending, next_code)

    assert await _flow(instance).recover(pending, "NOTACODE00") is None
    recovered = await _flow(instance).recover(pending, codes[0])
    assert recovered is not None
    assert recovered.user_id == signed_in.user_id
    assert await _flow(instance).recover(pending, codes[0]) is None


class _NoRemover:
    async def delete_identity(self, subject: str) -> None:
        raise AssertionError("no identity is removed here")


async def test_the_administrator_manages_local_logins(instance: str) -> None:
    """Covers: KAL-TEN-019"""
    out, err = io.StringIO(), io.StringIO()
    cli = tenant_admin.TenantAdminCli(AsyncSessionFactory.public, _NoRemover(), out=out, err=err)

    assert await cli.create_login("Owner@Example.com", admin=True) == 0
    created = out.getvalue().splitlines()[-1]
    first_password = created.rsplit(": ", 1)[1]
    assert "owner@example.com" in created
    assert await cli.create_login("owner@example.com", admin=False) == 1
    assert "already exists" in err.getvalue()

    async with AsyncSessionFactory.public() as public:
        identities = LocalIdentityService(public)
        row = await identities.authenticate("owner@example.com", first_password)
        assert row.is_instance_admin

    assert await cli.reset_password("owner@example.com") == 0
    second_password = out.getvalue().splitlines()[-1].rsplit(": ", 1)[1]
    assert second_password != first_password
    async with AsyncSessionFactory.public() as public:
        identities = LocalIdentityService(public)
        assert await identities.verify_password(row.id, second_password)
        assert not await identities.verify_password(row.id, first_password)
    assert await cli.reset_password("nobody@example.com") == 1

    assert await cli.logins() == 0
    listing = out.getvalue().splitlines()[-1].split("\t")
    assert listing[1:3] == ["owner@example.com", "admin"]

    assert await cli.registration(None) == 0
    assert out.getvalue().splitlines()[-1] == "registration closed"
    assert await cli.registration(RegistrationMode.OPEN) == 0
    assert out.getvalue().splitlines()[-1] == "registration open"


async def test_two_first_sign_ups_at_once_make_one_administrator(instance: str) -> None:
    """Covers: KAL-TEN-015"""
    outcomes = await asyncio.gather(
        RegistryAuthProvider().sign_up("first@example.com", PASSWORD),
        RegistryAuthProvider().sign_up("second@example.com", PASSWORD),
        return_exceptions=True,
    )

    created = [o for o in outcomes if not isinstance(o, BaseException)]
    refused = [o for o in outcomes if isinstance(o, BaseException)]
    assert len(created) == 1
    assert len(refused) == 1
    assert isinstance(refused[0], ValidationError)
    async with AsyncSessionFactory.public() as public:
        rows = await LocalIdentityService(public).list()
    assert [(r.email, r.is_instance_admin) for r in rows] == [
        (created[0].identity.email, True)  # type: ignore[union-attr]
    ]


async def test_an_overlong_password_is_refused_before_hashing(instance: str) -> None:
    """Covers: KAL-TEN-017"""
    await RegistryAuthProvider().sign_up(ADMIN, PASSWORD)
    with pytest.raises(UnauthorizedError, match="Invalid e-mail or password"):
        await RegistryAuthProvider().sign_in(ADMIN, "x" * 1025)
    await _set_mode(RegistrationMode.OPEN)
    with pytest.raises(ValidationError, match="at most"):
        await RegistryAuthProvider().sign_up("new@example.com", "x" * 1025)
    with pytest.raises(ValidationError, match="e-mail"):
        async with AsyncSessionFactory.public() as public:
            await LocalIdentityService(public).create("a@b@c", PASSWORD)


async def test_disabling_a_login_ends_its_sessions_and_tokens(instance: str) -> None:
    """Covers: KAL-TEN-017"""
    await RegistryAuthProvider().sign_up(ADMIN, PASSWORD)
    await _set_mode(RegistrationMode.OPEN)
    result = await RegistryAuthProvider().sign_up("member@example.com", PASSWORD)
    assert result.identity is not None
    signed_in = await _flow(instance).complete(result.identity)
    async with AsyncSessionFactory.public() as public:
        membership = await TenantService(public).get_member_by_subject(result.identity.subject)
    assert membership is not None
    with use_tenant(membership.context()):
        async with AsyncSessionFactory() as session:
            _token, raw = await ApiTokenService(session).create_token(
                user_id=signed_in.user_id, label="script"
            )
            assert await AuthService(session).sessions_valid_from(signed_in.user_id) is None

    identity_id = int(result.identity.subject.removeprefix("local:"))
    await set_login_disabled(identity_id, True)

    with use_tenant(membership.context()):
        async with AsyncSessionFactory() as session:
            watermark = await AuthService(session).sessions_valid_from(signed_in.user_id)
            assert await ApiTokenService(session).authenticate_bearer(raw) is None
    assert watermark is not None
    with pytest.raises(UnauthorizedError):
        await RegistryAuthProvider().sign_in("member@example.com", PASSWORD)

    await set_login_disabled(identity_id, False)
    again = await RegistryAuthProvider().sign_in("member@example.com", PASSWORD)
    assert isinstance(again, Identity)


async def test_deleting_a_family_keeps_the_administrators_login(instance: str) -> None:
    """Covers: KAL-TEN-017"""
    result = await RegistryAuthProvider().sign_up(ADMIN, PASSWORD)
    assert result.identity is not None
    await _set_mode(RegistrationMode.OPEN)
    member = await RegistryAuthProvider().sign_up("member@example.com", PASSWORD)
    assert member.identity is not None

    await RegistryAuthProvider().delete_identity(result.identity.subject)
    await RegistryAuthProvider().delete_identity(member.identity.subject)

    async with AsyncSessionFactory.public() as public:
        identities = LocalIdentityService(public)
        assert await identities.get_by_email(ADMIN) is not None
        assert await identities.get_by_email("member@example.com") is None


async def test_the_login_commands_refuse_another_backend(tmp_path: Path) -> None:
    """Covers: KAL-TEN-019"""
    async with multi_tenant_database() as _url:  # auth_backend="supabase"
        set_auth_provider(_NoRemover())  # type: ignore[arg-type]
        try:
            status = await tenant_admin._run(argparse.Namespace(command="logins"))
        finally:
            set_auth_provider(None)
    assert status == 2


async def test_the_data_passphrase_may_not_be_the_local_login_password(instance: str) -> None:
    """Covers: KAL-TEN-020"""
    result = await RegistryAuthProvider().sign_up(ADMIN, PASSWORD)
    assert result.identity is not None

    assert await is_local_login_password(result.identity.subject, PASSWORD)
    assert not await is_local_login_password(result.identity.subject, "another passphrase")
    # A Supabase member's password is the provider's: nothing to compare with.
    assert not await is_local_login_password("00000000-0000-4000-8000-000000000001", PASSWORD)


async def test_the_administrator_turns_a_members_second_factor_off(instance: str) -> None:
    """Covers: KAL-TEN-021"""
    result = await RegistryAuthProvider().sign_up(ADMIN, PASSWORD)
    assert result.identity is not None
    signed_in = await _flow(instance).complete(result.identity)
    async with AsyncSessionFactory.public() as public:
        membership = await TenantService(public).get_member_by_subject(result.identity.subject)
    assert membership is not None
    with use_tenant(membership.context()):
        async with AsyncSessionFactory() as session:
            mfa = MfaService(session)
            enrolment = await mfa.begin_enrolment(signed_in.user_id)
            totp = pyotp.TOTP(enrolment.secret, interval=TOTP_INTERVAL)
            await mfa.confirm_enrolment(signed_in.user_id, totp.now())
    assert isinstance(await RegistryAuthProvider().sign_in(ADMIN, PASSWORD), MfaRequired)

    out = io.StringIO()
    cli = tenant_admin.TenantAdminCli(
        AsyncSessionFactory.public, _NoRemover(), tenant_session=AsyncSessionFactory, out=out
    )
    assert await cli.reset_password(ADMIN, disable_mfa=True) == 0
    new_password = out.getvalue().splitlines()[-2].rsplit(": ", 1)[1]
    assert out.getvalue().splitlines()[-1] == "two-factor authentication: removed"

    assert isinstance(await RegistryAuthProvider().sign_in(ADMIN, new_password), Identity)
    with use_tenant(membership.context()):
        async with AsyncSessionFactory() as session:
            assert not await MfaService(session).is_enabled(signed_in.user_id)
            assert await AuthService(session).sessions_valid_from(signed_in.user_id) is not None

    assert await cli.reset_password(ADMIN, disable_mfa=True) == 0
    assert out.getvalue().splitlines()[-1] == "two-factor authentication: none"


ENV_TOKEN = "env-token-for-the-headless-api-0123"


async def _accounts_with(token: str) -> int:
    """The status of ``GET /accounts/`` with ``token``, sent as latin-1 bytes like any header."""
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(create_api_router())
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}".encode("latin-1")},
    ) as client:
        return (await client.get("/api/v1/accounts/")).status_code


async def test_the_environment_token_acts_as_the_administrator_in_their_family(
    instance: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Covers: KAL-TEN-022"""
    monkeypatch.setattr(settings, "api_token", ENV_TOKEN)
    monkeypatch.setattr("kaleta.api.deps.is_configured", lambda: True)
    assert await _accounts_with(ENV_TOKEN) == 401  # no administrator yet

    result = await RegistryAuthProvider().sign_up(ADMIN, PASSWORD)
    assert result.identity is not None
    assert await _accounts_with(ENV_TOKEN) == 401  # no family until the first sign-in

    await _flow(instance).complete(result.identity)
    assert await _accounts_with(ENV_TOKEN) == 200
    assert await _accounts_with(ENV_TOKEN[:-1] + "X") == 401
    assert await _accounts_with("é" * 20) == 401  # not a 500: compared as bytes

    async with AsyncSessionFactory.public() as public:
        membership = await TenantService(public).get_member_by_subject(result.identity.subject)
        assert membership is not None
        membership.member.status = TenantMemberStatus.REMOVED
        await public.commit()
    assert await _accounts_with(ENV_TOKEN) == 401
    async with AsyncSessionFactory.public() as public:
        membership = await TenantService(public).get_member_by_subject(result.identity.subject)
        assert membership is not None
        membership.member.status = TenantMemberStatus.ACTIVE
        await public.commit()
    assert await _accounts_with(ENV_TOKEN) == 200

    # The token follows the oldest enabled administrator: disable this one and
    # it is the second's, who has no family yet.
    async with AsyncSessionFactory.public() as public:
        await LocalIdentityService(public).create("second@example.com", PASSWORD, admin=True)
    identity_id = int(result.identity.subject.removeprefix("local:"))
    await set_login_disabled(identity_id, True)
    assert await _accounts_with(ENV_TOKEN) == 401
