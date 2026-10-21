# SPDX-License-Identifier: AGPL-3.0-or-later
"""InstanceAdminService — what the instance administrator may do (ADR-38 §5).

Covers: KAL-ADM-001, KAL-ADM-002, KAL-ADM-003, KAL-ADM-004, KAL-ADM-005, KAL-ADM-006,
KAL-ADM-008, KAL-ADM-011
"""

from __future__ import annotations

import io
import os
import time
from collections.abc import AsyncIterator
from dataclasses import replace
from pathlib import Path

import pyotp
import pytest
from sqlalchemy import select, text

from kaleta.auth.admin import verify_admin_credentials
from kaleta.auth.local_logins import set_login_disabled
from kaleta.auth.providers import RegistryAuthProvider, set_auth_provider
from kaleta.auth.revocation_cache import revocation_cache
from kaleta.auth.sign_in import SignedIn, SignInFlow
from kaleta.cli import tenant_admin
from kaleta.crypto import DataKey
from kaleta.db import AsyncSessionFactory
from kaleta.db.tenant_context import install_tenant_resolver, use_tenant
from kaleta.exceptions import ConflictError, NotFoundError, UnauthorizedError, ValidationError
from kaleta.models.tenant import AdminAction, AdminAuditEntry, Tenant, TenantStatus
from kaleta.schemas.identity import Identity, RegistrationMode
from kaleta.services import ApiTokenService, AuthService
from kaleta.services.instance_admin_service import InstanceAdminService
from kaleta.services.local_identity_service import LocalIdentityService
from kaleta.services.mfa_service import TOTP_INTERVAL, MfaService
from kaleta.services.tenant_service import TenantService
from tests.tenancy_helpers import MetadataProvisioner, multi_tenant_database

ADMIN = "admin@example.com"
JAN = "jan@example.com"
ANIA = "ania@example.com"
PASSWORD = "correct horse battery"


@pytest.fixture
async def instance(tmp_path: Path) -> AsyncIterator[str]:
    set_auth_provider(RegistryAuthProvider())
    try:
        async with multi_tenant_database(auth_backend="local") as url:
            yield url
    finally:
        set_auth_provider(None)


class _Flow(SignInFlow):
    """SignInFlow with the fast schema builder."""

    def __init__(self, url: str) -> None:
        super().__init__()
        self._url = url

    async def _membership(self, identity: Identity):  # type: ignore[no-untyped-def]
        async with AsyncSessionFactory.public() as public:
            service = TenantService(public, provisioner=MetadataProvisioner(self._url))
            return await service.membership_for_sign_in(identity)


async def _sign_in(url: str, email: str, password: str) -> SignedIn:
    identity = await RegistryAuthProvider().sign_in(email, password)
    assert isinstance(identity, Identity)
    return await _Flow(url).complete(identity)


async def _admin_subject(url: str) -> str:
    """The first sign-up: the instance administrator, with a family of their own."""
    result = await RegistryAuthProvider().sign_up(ADMIN, PASSWORD)
    assert result.identity is not None
    await _Flow(url).complete(result.identity)
    return result.identity.subject


def _service(public, url: str, actor: str | None, provisioner=None):  # type: ignore[no-untyped-def]
    return InstanceAdminService(
        public,
        actor=actor,
        auth_backend="local",
        remover=RegistryAuthProvider(),
        provisioner=provisioner or MetadataProvisioner(url),
    )


async def _schema_exists(schema: str) -> bool:
    async with AsyncSessionFactory.public() as public:
        found = await public.execute(
            text("SELECT 1 FROM information_schema.schemata WHERE schema_name = :s"),
            {"s": schema},
        )
        return found.scalar_one_or_none() is not None


async def _create_family(url: str, actor: str, name: str, owner: str) -> tuple[int, str]:
    async with AsyncSessionFactory.public() as public:
        created = await _service(public, url, actor).create_family(owner, name)
    return created.tenant_id, created.owner.password


async def test_only_an_instance_administrator_gets_the_service(instance: str) -> None:
    """Covers: KAL-ADM-001"""
    admin = await _admin_subject(instance)
    tenant_id, password = await _create_family(instance, admin, "Nowakowie", ANIA)
    member = await _sign_in(instance, ANIA, password)
    assert member.tenant is not None

    async with AsyncSessionFactory.public() as public:
        granted = await InstanceAdminService.for_actor(
            public,
            subject=admin,
            email=ADMIN,
            auth_backend="local",
            admin_emails=frozenset(),
            remover=RegistryAuthProvider(),
        )
        assert [f.tenant_id for f in await granted.families()][-1] == tenant_id
        with pytest.raises(NotFoundError):
            await InstanceAdminService.for_actor(
                public,
                subject=member.tenant.auth_subject,
                email=ANIA,
                auth_backend="local",
                admin_emails=frozenset({ANIA}),  # read only on a Supabase instance
                remover=RegistryAuthProvider(),
            )
        # Supabase: the operator's list decides; there are no local flags.
        supabase = await InstanceAdminService.for_actor(
            public,
            subject="00000000-0000-4000-8000-000000000009",
            email="Owner@Example.com",
            auth_backend="supabase",
            admin_emails=frozenset({"owner@example.com"}),
            remover=RegistryAuthProvider(),
        )
        assert supabase is not None
        with pytest.raises(NotFoundError):
            await InstanceAdminService.for_actor(
                public,
                subject=admin,
                email=ADMIN,
                auth_backend="supabase",
                admin_emails=frozenset({"owner@example.com"}),
                remover=RegistryAuthProvider(),
            )


async def test_a_family_is_created_with_a_one_time_password_for_its_owner(instance: str) -> None:
    """Covers: KAL-ADM-002"""
    admin = await _admin_subject(instance)

    tenant_id, password = await _create_family(instance, admin, " Kowalscy ", "Jan@Example.com")

    async with AsyncSessionFactory.public() as public:
        service = _service(public, instance, admin)
        family = await service.family(tenant_id)
        login = await service.login_by_email(JAN)
    assert family.name == "Kowalscy"
    assert family.owner_email == JAN
    assert family.members == 1
    assert family.status is TenantStatus.ACTIVE
    assert family.owner_signed_in is False
    assert login.must_change_password
    assert not login.is_admin

    signed_in = await _sign_in(instance, JAN, password)
    assert signed_in.tenant is not None
    assert signed_in.tenant.tenant_id == tenant_id
    async with AsyncSessionFactory.public() as public:
        assert (await _service(public, instance, admin).family(tenant_id)).owner_signed_in


async def test_a_family_needs_a_name_and_a_free_address(instance: str) -> None:
    """Covers: KAL-ADM-002"""
    admin = await _admin_subject(instance)
    async with AsyncSessionFactory.public() as public:
        service = _service(public, instance, admin)
        with pytest.raises(ValidationError):
            await service.create_family(JAN, "   ")
        with pytest.raises(ValidationError):
            await service.create_family(JAN, "x" * 101)
        with pytest.raises(ConflictError, match="already exists"):
            await service.create_family(ADMIN, "Kowalscy")
        assert [f.name for f in await service.families()] == [None]


async def test_suspend_resume_and_delete_a_family(instance: str) -> None:
    """Covers: KAL-ADM-003"""
    admin = await _admin_subject(instance)
    tenant_id, password = await _create_family(instance, admin, "Kowalscy", JAN)

    async with AsyncSessionFactory.public() as public:
        await _service(public, instance, admin).suspend(tenant_id)
    with pytest.raises(UnauthorizedError):
        await _sign_in(instance, JAN, password)

    async with AsyncSessionFactory.public() as public:
        await _service(public, instance, admin).resume(tenant_id)
    await _sign_in(instance, JAN, password)

    async with AsyncSessionFactory.public() as public:
        service = _service(public, instance, admin)
        with pytest.raises(ValidationError):
            await service.delete(tenant_id, typed="Kowalsk")
        with pytest.raises(ValidationError):
            await service.delete(tenant_id, typed=None)  # only kaleta-admin may skip it
        assert (await service.family(tenant_id)).status is TenantStatus.ACTIVE

        schema = (await public.get(Tenant, tenant_id)).schema_name  # type: ignore[union-attr]
        assert await _schema_exists(schema)
        deleted = await service.delete(tenant_id, typed="Kowalscy")

        assert deleted.identities_removed == 1
        assert not await _schema_exists(schema)
        assert await public.get(Tenant, tenant_id) is None
        assert await LocalIdentityService(public).get_by_email(JAN) is None
        assert await LocalIdentityService(public).get_by_email(ADMIN) is not None


async def test_a_family_that_signed_itself_up_is_confirmed_by_its_owners_address(
    instance: str,
) -> None:
    """Covers: KAL-ADM-003"""
    admin = await _admin_subject(instance)
    async with AsyncSessionFactory.public() as public:
        await LocalIdentityService(public).set_registration_mode(RegistrationMode.OPEN)
    result = await RegistryAuthProvider().sign_up(ANIA, PASSWORD)
    assert result.identity is not None
    signed_in = await _Flow(instance).complete(result.identity)
    assert signed_in.tenant is not None

    async with AsyncSessionFactory.public() as public:
        service = _service(public, instance, admin)
        family = await service.family(signed_in.tenant.tenant_id)
        assert family.name is None
        assert family.label == ANIA
        await service.delete(family.tenant_id, typed=ANIA)


async def test_a_password_reset_signs_the_members_browsers_out(instance: str) -> None:
    """Covers: KAL-ADM-004"""
    admin = await _admin_subject(instance)
    tenant_id, password = await _create_family(instance, admin, "Kowalscy", JAN)
    signed_in = await _sign_in(instance, JAN, password)
    async with AsyncSessionFactory.public() as public:
        identities = LocalIdentityService(public)
        row = await identities.get_by_email(JAN)
        assert row is not None
        await identities.set_password(row.id, PASSWORD)  # what the owner chose
        assert not (await identities.get(row.id)).must_change_password  # type: ignore[union-attr]

    async with AsyncSessionFactory.public() as public:
        reset = await _service(public, instance, admin).reset_password(row.id)

    assert reset.login.email == JAN
    assert reset.sessions_revoked
    assert reset.mfa_removed is None
    with pytest.raises(UnauthorizedError):
        await RegistryAuthProvider().sign_in(JAN, PASSWORD)
    assert isinstance(await RegistryAuthProvider().sign_in(JAN, reset.login.password), Identity)
    async with AsyncSessionFactory.public() as public:
        assert (await LocalIdentityService(public).get(row.id)).must_change_password  # type: ignore[union-attr]
        membership = await TenantService(public).get_member_by_subject(f"local:{row.id}")
    assert membership is not None and membership.tenant.id == tenant_id
    with use_tenant(membership.context()):
        async with AsyncSessionFactory() as session:
            assert await AuthService(session).sessions_valid_from(signed_in.user_id) is not None


async def test_the_last_administrator_stays_one(instance: str) -> None:
    """Covers: KAL-ADM-005"""
    admin = await _admin_subject(instance)
    await _create_family(instance, admin, "Kowalscy", JAN)
    async with AsyncSessionFactory.public() as public:
        service = _service(public, instance, admin)
        admin_row = await service.login_by_email(ADMIN)
        jan = await service.login_by_email(JAN)

        await service.set_admin(jan.identity_id, True)
        assert {r.email for r in await service.logins() if r.is_admin} == {ADMIN, JAN}

        await service.set_admin(admin_row.identity_id, False)
        assert [r.email for r in await service.logins() if r.is_admin] == [JAN]

        with pytest.raises(ValidationError, match="last administrator"):
            await service.set_admin(jan.identity_id, False)
        with pytest.raises(ValidationError, match="last administrator"):
            await service.set_disabled(jan.identity_id, True)
        assert [r.email for r in await service.logins() if r.is_admin] == [JAN]


async def test_disabling_a_member_of_another_family_forgets_their_own_watermark(
    instance: str,
) -> None:
    """Disabling a login from the panel runs in the administrator's family, but
    must forget the *disabled* member's cached revocation watermark — keyed by
    their own family, not the administrator's. Every family numbers its users
    from 1, so the user id alone names several people.

    Covers: KAL-ADM-011
    """
    admin = await _admin_subject(instance)
    jan_tenant_id, password = await _create_family(instance, admin, "Kowalscy", JAN)
    signed_in = await _sign_in(instance, JAN, password)
    jan_user_id = signed_in.user_id

    async with AsyncSessionFactory.public() as public:
        service = _service(public, instance, admin)
        jan = await service.login_by_email(JAN)
        tenants = TenantService(public)
        admin_membership = await tenants.get_member_by_subject(admin)
        jan_membership = await tenants.get_member_by_subject(f"local:{jan.identity_id}")
    assert admin_membership is not None
    assert jan_membership is not None
    admin_tenant_id = admin_membership.tenant.id
    assert admin_tenant_id != jan_tenant_id  # two separate families

    revocation_cache.clear()
    # Prime both families' caches for Jan's user id: his own family's entry (the
    # one that must be dropped) and a decoy under the administrator's family (the
    # one the bug drops instead — they share the numeric user id).
    with use_tenant(jan_membership.context()):
        assert await revocation_cache.valid_from(jan_user_id) is None
    with use_tenant(admin_membership.context()):
        await revocation_cache.valid_from(jan_user_id)

    # Disabling runs with the administrator's family as the current tenant.
    with use_tenant(admin_membership.context()):
        await set_login_disabled(jan.identity_id, True, actor=admin)

    # The administrator's own entry is left alone...
    assert (admin_tenant_id, jan_user_id) in revocation_cache._entries
    # ...and Jan's own family's entry was dropped, so his next guard reads the
    # raised watermark and his session is revoked at once.
    with use_tenant(jan_membership.context()):
        assert await revocation_cache.valid_from(jan_user_id) is not None


async def test_every_action_leaves_an_audit_row_without_the_targets_address(
    instance: str,
) -> None:
    """Covers: KAL-ADM-006"""
    admin = await _admin_subject(instance)
    tenant_id, _password = await _create_family(instance, admin, "Kowalscy", JAN)
    async with AsyncSessionFactory.public() as public:
        service = _service(public, instance, admin)
        jan = await service.login_by_email(JAN)
        await service.suspend(tenant_id)
        await service.reset_password(jan.identity_id)
        await service.set_registration_mode(RegistrationMode.OPEN)
        await service.set_registration_mode(RegistrationMode.OPEN)  # no change, no row
        trail = await service.audit_trail()

    assert [(e.action, e.tenant_id, e.identity_id, e.detail) for e in trail] == [
        (AdminAction.REGISTRATION_CHANGED, None, None, "open"),
        # Suspended, not closed: the reset signs Jan's browsers out there too.
        (AdminAction.SESSIONS_REVOKED, None, jan.identity_id, None),
        (AdminAction.PASSWORD_RESET, None, jan.identity_id, None),
        (AdminAction.FAMILY_SUSPENDED, tenant_id, None, None),
        (AdminAction.FAMILY_CREATED, tenant_id, jan.identity_id, None),
        (AdminAction.LOGIN_CREATED, None, jan.identity_id, None),
    ]
    assert {e.actor for e in trail} == {admin}
    for entry in trail:
        assert JAN not in " ".join(str(v) for v in vars(entry).values())

    out = io.StringIO()
    cli = tenant_admin.TenantAdminCli(AsyncSessionFactory.public, RegistryAuthProvider(), out=out)
    assert await cli.resume(tenant_id) == 0
    async with AsyncSessionFactory.public() as public:
        newest = (
            (await public.execute(select(AdminAuditEntry).order_by(AdminAuditEntry.id.desc())))
            .scalars()
            .first()
        )
    assert newest is not None
    assert (newest.action, newest.actor, newest.tenant_id) == (
        AdminAction.FAMILY_RESUMED,
        None,
        tenant_id,
    )


async def test_a_family_whose_provisioning_fails_leaves_nothing_behind(instance: str) -> None:
    """Covers: KAL-ADM-002"""
    admin = await _admin_subject(instance)
    failing = MetadataProvisioner(instance, fail_first=True)
    async with AsyncSessionFactory.public() as public:
        with pytest.raises(RuntimeError, match="simulated crash"):
            await _service(public, instance, admin, failing).create_family(JAN, "Kowalscy")
    async with AsyncSessionFactory.public() as public:
        assert await LocalIdentityService(public).get_by_email(JAN) is None
        assert len(await _service(public, instance, admin).families()) == 1  # the admin's
        assert await _service(public, instance, admin).audit_trail() == []

    tenant_id, _password = await _create_family(instance, admin, "Kowalscy", JAN)
    async with AsyncSessionFactory.public() as public:
        assert (await _service(public, instance, admin).family(tenant_id)).name == "Kowalscy"


async def test_a_login_disabled_while_its_family_is_suspended_stays_out_after_resume(
    instance: str,
) -> None:
    """Covers: KAL-ADM-003"""
    admin = await _admin_subject(instance)
    tenant_id, password = await _create_family(instance, admin, "Kowalscy", JAN)
    signed_in = await _sign_in(instance, JAN, password)
    async with AsyncSessionFactory.public() as public:
        membership = await TenantService(public).get_member_by_subject(
            signed_in.tenant.auth_subject  # type: ignore[union-attr]
        )
        jan = await _service(public, instance, admin).login_by_email(JAN)
    assert membership is not None
    with use_tenant(membership.context()):
        async with AsyncSessionFactory() as session:
            _token, raw = await ApiTokenService(session).create_token(
                user_id=signed_in.user_id, label="script"
            )

    async with AsyncSessionFactory.public() as public:
        await _service(public, instance, admin).suspend(tenant_id)
    await set_login_disabled(jan.identity_id, True, actor=admin)
    async with AsyncSessionFactory.public() as public:
        await _service(public, instance, admin).resume(tenant_id)

    with use_tenant(membership.context()):
        async with AsyncSessionFactory() as session:
            assert await ApiTokenService(session).authenticate_bearer(raw) is None
            assert await AuthService(session).sessions_valid_from(signed_in.user_id) is not None
    with pytest.raises(UnauthorizedError):
        await RegistryAuthProvider().sign_in(JAN, password)


async def test_turning_mfa_off_in_a_suspended_family_changes_nothing(instance: str) -> None:
    """Covers: KAL-ADM-004"""
    admin = await _admin_subject(instance)
    tenant_id, password = await _create_family(instance, admin, "Kowalscy", JAN)
    signed_in = await _sign_in(instance, JAN, password)
    async with AsyncSessionFactory.public() as public:
        membership = await TenantService(public).get_member_by_subject(
            signed_in.tenant.auth_subject  # type: ignore[union-attr]
        )
        jan = await _service(public, instance, admin).login_by_email(JAN)
    assert membership is not None
    with use_tenant(membership.context()):
        async with AsyncSessionFactory() as session:
            mfa = MfaService(session)
            enrolment = await mfa.begin_enrolment(signed_in.user_id)
            totp = pyotp.TOTP(enrolment.secret, interval=TOTP_INTERVAL)
            await mfa.confirm_enrolment(signed_in.user_id, totp.now())

    async with AsyncSessionFactory.public() as public:
        service = _service(public, instance, admin)
        await service.suspend(tenant_id)
        with pytest.raises(ValidationError, match="resume the family first"):
            await service.reset_password(jan.identity_id, disable_mfa=True)
    async with AsyncSessionFactory.public() as public:
        assert await LocalIdentityService(public).verify_password(jan.identity_id, password)

    async with AsyncSessionFactory.public() as public:
        service = _service(public, instance, admin)
        await service.resume(tenant_id)
        reset = await service.reset_password(jan.identity_id, disable_mfa=True)
        trail = [e.action for e in await service.audit_trail(limit=3)]
    assert reset.mfa_removed is True
    assert reset.sessions_revoked
    assert trail == [
        AdminAction.MFA_DISABLED,
        AdminAction.SESSIONS_REVOKED,
        AdminAction.PASSWORD_RESET,
    ]


async def test_login_and_family_actions_are_audited(instance: str) -> None:
    """Covers: KAL-ADM-006"""
    admin = await _admin_subject(instance)
    tenant_id, _password = await _create_family(instance, admin, "Kowalscy", JAN)
    async with AsyncSessionFactory.public() as public:
        service = _service(public, instance, admin)
        ania = await service.create_login(ANIA, admin=True)
        await service.set_admin(ania.identity_id, False)
        await service.set_disabled(ania.identity_id, True)
        await service.set_disabled(ania.identity_id, False)
        await service.delete(tenant_id, typed="Kowalscy")
        trail = await service.audit_trail(limit=6)

    assert [(e.action, e.tenant_id, e.identity_id) for e in trail] == [
        (AdminAction.FAMILY_DELETED, tenant_id, None),
        (AdminAction.LOGIN_ENABLED, None, ania.identity_id),
        (AdminAction.LOGIN_DISABLED, None, ania.identity_id),
        (AdminAction.ADMIN_REVOKED, None, ania.identity_id),
        (AdminAction.ADMIN_GRANTED, None, ania.identity_id),
        (AdminAction.LOGIN_CREATED, None, ania.identity_id),
    ]


async def test_a_family_created_from_an_unlocked_session_gets_none_of_its_key(
    tmp_path: Path,
) -> None:
    """Covers: KAL-ADM-002 — the panel runs in the administrator's own unlocked family.

    What provisioning writes in the new schema (the owner's ``users`` row and
    its audit row) must not be sealed with the administrator's data key: the
    owner could never read it, and their passphrase setup fails re-encrypting it.
    """
    set_auth_provider(RegistryAuthProvider())
    try:
        async with multi_tenant_database(auth_backend="local", encryption="passphrase") as url:
            admin = await _admin_subject(url)
            async with AsyncSessionFactory.public() as public:
                membership = await TenantService(public).get_member_by_subject(admin)
            assert membership is not None
            admin_key = DataKey(dek=os.urandom(32), version=1)
            unlocked = replace(membership.context(), key_ring=admin_key)
            install_tenant_resolver(lambda: unlocked)  # what the UI's page guard installs
            try:
                tenant_id, _password = await _create_family(url, admin, "Kowalscy", JAN)
            finally:
                install_tenant_resolver(None)
            async with AsyncSessionFactory.public() as public:
                schema = (await public.get(Tenant, tenant_id)).schema_name  # type: ignore[union-attr]
                formats = (
                    (
                        await public.execute(
                            text(
                                f'SELECT get_byte(new_data, 0) FROM "{schema}".audit_log '
                                "WHERE new_data IS NOT NULL"
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
    finally:
        set_auth_provider(None)
    assert formats  # the owner's users row was audited
    assert set(formats) == {0}  # plaintext-while-locked, not sealed under the admin's key


async def test_the_step_up_needs_the_password_and_with_two_factor_a_code(instance: str) -> None:
    """Covers: KAL-ADM-008"""
    admin = await _admin_subject(instance)
    async with AsyncSessionFactory.public() as public:
        membership = await TenantService(public).get_member_by_subject(admin)
    assert membership is not None and membership.member.user_id is not None
    user_id = membership.member.user_id

    async def proves(password: str, code: str = "", *, needs_code: bool = False) -> bool:
        with use_tenant(membership.context()):
            return await verify_admin_credentials(
                admin, ADMIN, user_id, password, code, needs_code=needs_code
            )

    assert await proves(PASSWORD)
    assert not await proves("not the password")

    with use_tenant(membership.context()):
        async with AsyncSessionFactory() as session:
            mfa = MfaService(session)
            enrolment = await mfa.begin_enrolment(user_id)
            totp = pyotp.TOTP(enrolment.secret, interval=TOTP_INTERVAL)
            await mfa.confirm_enrolment(user_id, totp.now())
    assert not await proves(PASSWORD, "000000", needs_code=True)
    # The enrolment spent the current code; the next one is unused.
    fresh = totp.at(int(time.time()) + TOTP_INTERVAL)
    assert not await proves("not the password", fresh, needs_code=True)
    assert await proves(PASSWORD, fresh, needs_code=True)
