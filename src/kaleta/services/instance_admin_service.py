# SPDX-License-Identifier: AGPL-3.0-or-later
"""What the instance administrator may do, for the panel and ``kaleta-admin``.

ADR-38 §5: whoever runs an instance creates, suspends, resumes and deletes
families, decides who may sign up and helps a member who forgot their login
password — and sees e-mail addresses, counts and statuses, never a family's
data. Both the ``/admin`` page and the CLI go through this class, so both
write the same ``public.admin_audit`` row and log line for every action.

Works on a *public* session. Reaching into a family's schema (signing a
member's browsers out, turning their second factor off) goes through the
``tenant_session`` factory under that family's ``TenantContext``.

An instance is administered by its operator at a shell (:meth:`for_operator`,
the CLI) or by an administrator signed in to the panel (:meth:`for_actor`):
``local`` logins carry ``is_instance_admin``, a ``supabase`` instance names its
administrators in ``KALETA_INSTANCE_ADMINS``. :meth:`for_actor` raises
``NotFoundError`` for anyone else — the panel answers 404, not "forbidden".
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta import __version__
from kaleta.db.tenant_context import use_tenant
from kaleta.exceptions import NotFoundError, ValidationError
from kaleta.models.tenant import (
    AdminAction,
    AdminAuditEntry,
    LocalIdentity,
    Tenant,
    TenantMember,
    TenantMemberStatus,
    TenantRole,
    TenantStatus,
)
from kaleta.schemas.identity import Identity, RegistrationMode
from kaleta.services.account_deletion_service import (
    AccountDeletion,
    AccountDeletionService,
    IdentityRemover,
)
from kaleta.services.api_token_service import ApiTokenService
from kaleta.services.auth_service import AuthService
from kaleta.services.local_identity_service import (
    LocalIdentityService,
    identity_id_of,
    normalise_email,
    subject_of,
)
from kaleta.services.mfa_service import MfaService
from kaleta.services.tenant_service import SchemaProvisioner, TenantMembership, TenantService

logger = logging.getLogger(__name__)

AuthBackend = Literal["local", "supabase"]

#: ``tenants.name`` is free text from the administrator; a label, not an essay.
FAMILY_NAME_MAX = 100
#: Entropy of a one-time password (``secrets.token_urlsafe`` bytes → 16 chars).
_ONE_TIME_PASSWORD_BYTES = 12


@dataclass(frozen=True)
class FamilyRow:
    """One family as the administrator sees it: no data, only registry facts."""

    tenant_id: int
    name: str | None
    owner_email: str | None
    members: int
    status: TenantStatus
    #: ``False`` while a family made by the administrator waits for its
    #: owner's first sign-in (shown as "pending"); ``None`` when the owner's
    #: login is another provider's.
    owner_signed_in: bool | None
    created_at: datetime
    last_seen_at: datetime | None

    @property
    def label(self) -> str:
        """What the administrator types to confirm deleting this family."""
        return self.name or self.owner_email or f"#{self.tenant_id}"


@dataclass(frozen=True)
class LoginRow:
    """One ``local`` login."""

    identity_id: int
    email: str
    is_admin: bool
    disabled: bool
    must_change_password: bool
    last_login_at: datetime | None
    tenant_id: int | None


@dataclass(frozen=True)
class OneTimePassword:
    """A password made for someone else — shown once, changed at the next sign-in."""

    identity_id: int
    email: str
    password: str


@dataclass(frozen=True)
class CreatedFamily:
    tenant_id: int
    owner: OneTimePassword


@dataclass(frozen=True)
class PasswordReset:
    login: OneTimePassword
    #: The login belongs to a family (it has signed in at least once).
    in_family: bool
    #: The member's browser sessions were signed out (they belong to an
    #: active family).
    sessions_revoked: bool
    #: ``True`` removed, ``False`` there was none, ``None`` not asked.
    mfa_removed: bool | None


@dataclass(frozen=True)
class RevokedMember:
    """A member whose sessions and tokens were revoked in their family."""

    tenant_id: int
    user_id: int


@dataclass(frozen=True)
class InstanceInfo:
    version: str
    auth_backend: AuthBackend
    families: int
    logins: int | None
    registration: RegistrationMode | None


class InstanceAdminService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        actor: str | None,
        auth_backend: AuthBackend,
        remover: IdentityRemover,
        provisioner: SchemaProvisioner | None = None,
        tenant_session: Callable[[], AsyncSession] | None = None,
    ) -> None:
        self.session = session
        self._actor = actor
        self._backend: AuthBackend = auth_backend
        self._remover = remover
        self._tenant_session = tenant_session
        self._tenants = TenantService(
            session, provisioner=provisioner, tenant_session=tenant_session
        )
        self._logins = LocalIdentityService(session)

    # ── Who may ──────────────────────────────────────────────────────────────

    @classmethod
    def for_operator(
        cls,
        session: AsyncSession,
        *,
        auth_backend: AuthBackend,
        remover: IdentityRemover,
        provisioner: SchemaProvisioner | None = None,
        tenant_session: Callable[[], AsyncSession] | None = None,
    ) -> InstanceAdminService:
        """``kaleta-admin``: a shell on the host is the authority."""
        return cls(
            session,
            actor=None,
            auth_backend=auth_backend,
            remover=remover,
            provisioner=provisioner,
            tenant_session=tenant_session,
        )

    @classmethod
    async def for_actor(
        cls,
        session: AsyncSession,
        *,
        subject: str,
        email: str,
        auth_backend: AuthBackend,
        admin_emails: frozenset[str],
        remover: IdentityRemover,
        provisioner: SchemaProvisioner | None = None,
        tenant_session: Callable[[], AsyncSession] | None = None,
    ) -> InstanceAdminService:
        """The panel's service for a signed-in administrator; ``NotFoundError`` otherwise."""
        if not await is_instance_admin(
            session,
            subject=subject,
            email=email,
            auth_backend=auth_backend,
            admin_emails=admin_emails,
        ):
            msg = "Not found."
            # The page's initial load / refresh catch this by type (404 /
            # redirect, which ignore the key); but a panel *action* runs
            # ``for_actor`` inside ``admin._act``'s ``except KaletaError`` arm
            # (an administrator demoted mid-session), so the toast localizes.
            raise NotFoundError(msg, message_key="errors.instance_admin.not_found")
        return cls(
            session,
            actor=subject,
            auth_backend=auth_backend,
            remover=remover,
            provisioner=provisioner,
            tenant_session=tenant_session,
        )

    # ── Instance ─────────────────────────────────────────────────────────────

    async def info(self) -> InstanceInfo:
        families = await self.session.execute(select(func.count()).select_from(Tenant))
        local = self._backend == "local"
        return InstanceInfo(
            version=__version__,
            auth_backend=self._backend,
            families=int(families.scalar_one()),
            logins=await self._logins.count() if local else None,
            registration=await self._logins.registration_mode() if local else None,
        )

    async def registration_mode(self) -> RegistrationMode:
        self._require_local()
        return await self._logins.registration_mode()

    async def set_registration_mode(self, mode: RegistrationMode) -> None:
        self._require_local()
        if mode is await self._logins.registration_mode():
            return
        await self._logins.set_registration_mode(mode)
        await self._audit(AdminAction.REGISTRATION_CHANGED, detail=mode.value)

    # ── Families ─────────────────────────────────────────────────────────────

    async def families(self) -> list[FamilyRow]:
        counts = (
            select(TenantMember.tenant_id, func.count(TenantMember.id).label("n"))
            .where(TenantMember.status != TenantMemberStatus.REMOVED)
            .group_by(TenantMember.tenant_id)
            .subquery()
        )
        tenants = await self.session.execute(
            select(Tenant, func.coalesce(counts.c.n, 0))
            .outerjoin(counts, counts.c.tenant_id == Tenant.id)
            .order_by(Tenant.id)
        )
        owners = await self.session.execute(
            select(TenantMember).where(TenantMember.role == TenantRole.OWNER)
        )
        owner_of = {m.tenant_id: m for m in owners.scalars().all()}
        last_login = await self._last_logins()
        rows: list[FamilyRow] = []
        for tenant, members in tenants.all():
            owner = owner_of.get(tenant.id)
            signed_in: bool | None = None
            if owner is not None:
                identity_id = identity_id_of(owner.auth_subject)
                if identity_id is not None and identity_id in last_login:
                    signed_in = last_login[identity_id] is not None
            rows.append(
                FamilyRow(
                    tenant_id=tenant.id,
                    name=tenant.name,
                    owner_email=owner.email if owner is not None else None,
                    members=int(members),
                    status=tenant.status,
                    owner_signed_in=signed_in,
                    created_at=tenant.created_at,
                    last_seen_at=tenant.last_seen_at,
                )
            )
        return rows

    async def family(self, tenant_id: int) -> FamilyRow:
        for row in await self.families():
            if row.tenant_id == tenant_id:
                return row
        msg = f"Tenant {tenant_id} not found"
        # Reached from the admin panel's "Delete" flow (a family deleted
        # concurrently) → ``admin._act`` → ``notify_kaleta_error``.
        raise NotFoundError(
            msg,
            message_key="errors.instance_admin.family_not_found",
            params={"tenant_id": tenant_id},
        )

    async def create_family(self, owner_email: str, name: str) -> CreatedFamily:
        """A login for the owner with a one-time password, and their family, now.

        Provisioned at once rather than at the owner's first sign-in, so the
        family has its name and is listed (as pending) before anyone signs in.
        The owner sets the data passphrase at that first sign-in, as after a
        sign-up.
        """
        self._require_local()
        label = name.strip()
        if not label:
            msg = "Give the family a name."
            raise ValidationError(msg, message_key="errors.instance_admin.family_name_required")
        if len(label) > FAMILY_NAME_MAX:
            msg = f"A family name is at most {FAMILY_NAME_MAX} characters."
            raise ValidationError(
                msg,
                message_key="errors.instance_admin.family_name_too_long",
                params={"max": FAMILY_NAME_MAX},
            )
        password = _one_time_password()
        login = await self._logins.create(owner_email, password, must_change=True)
        identity = Identity(subject=login.subject, email=login.email, email_verified=True)
        try:
            tenant = await self._tenants.provision(identity)
            tenant.name = label
            await self.session.commit()
        except BaseException:
            # Nobody will ever see this password: undo the login and whatever
            # part of the family exists, so the address can simply be tried again.
            await self.session.rollback()
            await self._undo_family_of(login.id)
            raise
        await self._audit(AdminAction.LOGIN_CREATED, identity_id=login.id)
        await self._audit(AdminAction.FAMILY_CREATED, tenant_id=tenant.id, identity_id=login.id)
        return CreatedFamily(
            tenant_id=tenant.id,
            owner=OneTimePassword(identity_id=login.id, email=login.email, password=password),
        )

    async def suspend(self, tenant_id: int) -> Tenant:
        tenant = await self._tenants.suspend(tenant_id)
        await self._audit(AdminAction.FAMILY_SUSPENDED, tenant_id=tenant_id)
        return tenant

    async def resume(self, tenant_id: int) -> Tenant:
        tenant = await self._tenants.resume(tenant_id)
        await self._audit(AdminAction.FAMILY_RESUMED, tenant_id=tenant_id)
        return tenant

    async def delete(self, tenant_id: int, *, typed: str | None) -> AccountDeletion:
        """Delete a family: its members' identities, its schema, its registry rows.

        The panel passes what the administrator typed, which must be the
        family's :attr:`FamilyRow.label`. ``None`` is the CLI's ``--yes``,
        accepted only from the operator.
        """
        family = await self.family(tenant_id)
        if typed is None:
            if self._actor is not None:
                # ``typed`` is ``None`` only from the CLI's ``--yes`` (the panel
                # always submits a string); this guard is operator-shell-only.
                msg = "Type the family's name to delete it."
                raise ValidationError(msg)
        elif typed.strip() != family.label:
            msg = "The name you typed is not this family's."
            # Reached from the admin panel's delete dialog → ``admin._act``.
            raise ValidationError(msg, message_key="errors.instance_admin.family_name_mismatch")
        deleted = await AccountDeletionService(
            self.session, self._remover, tenant_service=self._tenants
        ).delete(tenant_id)
        await self._audit(AdminAction.FAMILY_DELETED, tenant_id=tenant_id)
        return deleted

    # ── Logins (``local``) ───────────────────────────────────────────────────

    async def logins(self) -> list[LoginRow]:
        self._require_local()
        members = await self.session.execute(select(TenantMember))
        tenant_of = {m.auth_subject: m.tenant_id for m in members.scalars().all()}
        return [
            LoginRow(
                identity_id=row.id,
                email=row.email,
                is_admin=row.is_instance_admin,
                disabled=row.disabled,
                must_change_password=row.must_change_password,
                last_login_at=row.last_login_at,
                tenant_id=tenant_of.get(row.subject),
            )
            for row in await self._logins.list()
        ]

    async def create_login(self, email: str, *, admin: bool) -> OneTimePassword:
        """A login of no family yet: it gets one at its first sign-in."""
        self._require_local()
        password = _one_time_password()
        row = await self._logins.create(email, password, admin=admin, must_change=True)
        await self._audit(AdminAction.LOGIN_CREATED, identity_id=row.id)
        if admin:
            await self._audit(AdminAction.ADMIN_GRANTED, identity_id=row.id)
        return OneTimePassword(identity_id=row.id, email=row.email, password=password)

    async def login_by_email(self, email: str) -> LoginRow:
        address = normalise_email(email)
        for row in await self.logins():
            if row.email == address:
                return row
        msg = f"No login {email!r}."
        raise NotFoundError(msg)

    async def set_disabled(self, identity_id: int, disabled: bool) -> RevokedMember | None:
        """Refuse or allow a login's sign-ins; when refusing, end what it holds.

        Sessions and API tokens are revoked in an active *or suspended* family:
        nothing re-checks a login after sign-in, so a family resumed later must
        not bring a disabled member's old browsers and tokens back. Returns the
        member whose were revoked, so the caller can drop what *this process*
        keeps for them (the revocation cache, the unlocked key).
        """
        self._require_local()
        await self._logins.set_disabled(identity_id, disabled)
        membership = await self._family_member(identity_id) if disabled else None
        if membership is not None and membership.member.user_id is not None:
            user_id = membership.member.user_id
            with use_tenant(membership.context()):
                async with self._require_tenant_session()() as session:
                    await AuthService(session).revoke_sessions(user_id)
                    await ApiTokenService(session).revoke_all(user_id=user_id)
        await self._audit(
            AdminAction.LOGIN_DISABLED if disabled else AdminAction.LOGIN_ENABLED,
            identity_id=identity_id,
        )
        if membership is None or membership.member.user_id is None:
            return None
        return RevokedMember(tenant_id=membership.tenant.id, user_id=membership.member.user_id)

    async def set_admin(self, identity_id: int, admin: bool) -> None:
        self._require_local()
        await self._logins.set_admin(identity_id, admin)
        await self._audit(
            AdminAction.ADMIN_GRANTED if admin else AdminAction.ADMIN_REVOKED,
            identity_id=identity_id,
        )

    async def reset_password(self, identity_id: int, *, disable_mfa: bool = False) -> PasswordReset:
        """A one-time password the member must change at the next sign-in.

        Every browser session of theirs is signed out first (KAL-AUTH-028),
        in an active or suspended family; API bearer tokens stay. If that
        fails, the password is left as it was. ``disable_mfa`` also removes
        their second factor — refused for a family that is not active, whose
        schema may be one that did not migrate (nothing is changed then).
        """
        self._require_local()
        login = await self._logins.get(identity_id)
        if login is None:
            msg = "No such login."
            # Reached from the admin panel's "Reset password" action (a login
            # removed concurrently) → ``admin._act`` → ``notify_kaleta_error``.
            raise NotFoundError(msg, message_key="errors.instance_admin.login_not_found")
        membership = await self._tenants.get_member_by_subject(subject_of(identity_id))
        in_family = membership is not None and membership.member.user_id is not None
        active = (
            in_family
            and membership is not None
            and (membership.tenant.status is TenantStatus.ACTIVE)
        )
        if disable_mfa and in_family and not active and membership is not None:
            msg = (
                f"Family {membership.tenant.id} is {membership.tenant.status.value}; "
                "two-factor authentication was left on — resume the family first."
            )
            raise ValidationError(msg)
        family = await self._family_member(identity_id)
        revoked = False
        if family is not None:
            await self._revoke_in_family(family)
            revoked = True
        password = _one_time_password()
        await self._logins.set_password(identity_id, password, must_change=True)
        await self._audit(AdminAction.PASSWORD_RESET, identity_id=identity_id)
        if revoked:
            await self._audit(AdminAction.SESSIONS_REVOKED, identity_id=identity_id)
        removed: bool | None = None
        if disable_mfa:
            removed = False
            if active and membership is not None:
                removed = await self._disable_mfa_in_family(membership)
                if removed:
                    await self._audit(AdminAction.MFA_DISABLED, identity_id=identity_id)
        return PasswordReset(
            login=OneTimePassword(identity_id=login.id, email=login.email, password=password),
            in_family=in_family,
            sessions_revoked=revoked,
            mfa_removed=removed,
        )

    async def revoke_sessions(self, identity_id: int) -> bool:
        """Sign every browser of this login out; ``False`` when it has no family."""
        self._require_local()
        membership = await self._family_member(identity_id)
        if membership is None:
            return False
        await self._revoke_in_family(membership)
        await self._audit(AdminAction.SESSIONS_REVOKED, identity_id=identity_id)
        return True

    # ── Audit ────────────────────────────────────────────────────────────────

    async def audit_trail(self, limit: int = 50) -> list[AdminAuditEntry]:
        result = await self.session.execute(
            select(AdminAuditEntry).order_by(AdminAuditEntry.id.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def _audit(
        self,
        action: AdminAction,
        *,
        tenant_id: int | None = None,
        identity_id: int | None = None,
        detail: str | None = None,
    ) -> None:
        self.session.add(
            AdminAuditEntry(
                actor=self._actor,
                action=action,
                tenant_id=tenant_id,
                identity_id=identity_id,
                detail=detail,
            )
        )
        await self.session.commit()
        logger.info(
            "Instance admin %s: %s (family %s, login %s%s)",
            self._actor or "kaleta-admin",
            action.value,
            tenant_id if tenant_id is not None else "-",
            identity_id if identity_id is not None else "-",
            f", {detail}" if detail else "",
        )

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _require_local(self) -> None:
        if self._backend != "local":
            msg = "This instance's logins live in Supabase; manage them there."
            raise ValidationError(msg)

    def _require_tenant_session(self) -> Callable[[], AsyncSession]:
        if self._tenant_session is None:
            from kaleta.db import AsyncSessionFactory

            self._tenant_session = AsyncSessionFactory
        return self._tenant_session

    async def _last_logins(self) -> dict[int, datetime | None]:
        if self._backend != "local":
            return {}
        result = await self.session.execute(select(LocalIdentity.id, LocalIdentity.last_login_at))
        return {row[0]: row[1] for row in result.all()}

    async def _family_member(self, identity_id: int) -> TenantMembership | None:
        """The login's family, if its sessions can be revoked there.

        Active or suspended: a suspended family can be resumed, and must not
        get a revoked member's sessions back. ``users.sessions_valid_from``
        is in every schema's history, so even one suspended for a failed
        migration has it. Families being provisioned, re-keyed or deleted are
        left alone.
        """
        membership = await self._tenants.get_member_by_subject(subject_of(identity_id))
        if (
            membership is None
            or membership.member.user_id is None
            or membership.tenant.status not in (TenantStatus.ACTIVE, TenantStatus.SUSPENDED)
        ):
            return None
        return membership

    async def _undo_family_of(self, identity_id: int) -> None:
        membership = await self._tenants.get_member_by_subject(subject_of(identity_id))
        if membership is not None:
            await self._tenants.delete(membership.tenant.id)
        await self._logins.delete(identity_id)

    async def _revoke_in_family(self, membership: TenantMembership) -> None:
        user_id = membership.member.user_id
        if user_id is None:
            return
        with use_tenant(membership.context()):
            async with self._require_tenant_session()() as session:
                await AuthService(session).revoke_sessions(user_id)

    async def _disable_mfa_in_family(self, membership: TenantMembership) -> bool:
        user_id = membership.member.user_id
        if user_id is None:
            return False
        with use_tenant(membership.context()):
            async with self._require_tenant_session()() as session:
                return await MfaService(session).disable_for_admin(user_id)


async def is_instance_admin(
    session: AsyncSession,
    *,
    subject: str,
    email: str,
    auth_backend: AuthBackend,
    admin_emails: frozenset[str],
) -> bool:
    """Whether this signed-in identity administers the instance — asked on every call."""
    if auth_backend == "supabase":
        return normalise_email(email) in admin_emails
    identity_id = identity_id_of(subject)
    if identity_id is None:
        return False
    row = await LocalIdentityService(session).get(identity_id)
    return row is not None and row.is_instance_admin and not row.disabled


def _one_time_password() -> str:
    return secrets.token_urlsafe(_ONE_TIME_PASSWORD_BYTES)
