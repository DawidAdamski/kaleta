# SPDX-License-Identifier: AGPL-3.0-or-later
"""A household: up to ten members on one family's data (``hosted-household-sharing``).

The owner invites by e-mail and is handed a link to pass on; the invitee signs
up through it, sets a data passphrase (which makes their keypair) and waits as
``pending``; the owner approves by sealing the household's data key to that
keypair. Removing a member re-keys the household (:class:`HouseholdRekey`), so
what they could once open, they cannot open from then on.

:class:`HouseholdService` is one member acting in their own household;
:class:`HouseholdInvitations` is what an invitation link may do before anyone
is signed in. Both work on a *public* session (the registry), and reach the
family's schema for its ``users`` rows and the re-key.

The data key comes from the caller — the acting member's unlocked session —
and is never stored: approving and re-keying need it in hand, which is why the
owner must be unlocked to do either.
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import Update, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.config import settings
from kaleta.crypto import DataKey, fingerprint, generate_dek, key_ring, seal, tenant_member_ref
from kaleta.db.tenant_context import TenantContext, use_tenant
from kaleta.db.types import also_read_under, use_data_key
from kaleta.exceptions import (
    ConflictError,
    NotFoundError,
    TenantLockedError,
    UnauthorizedError,
    ValidationError,
)
from kaleta.models.tenant import (
    Tenant,
    TenantInvite,
    TenantMember,
    TenantMemberStatus,
    TenantRole,
    TenantStatus,
)
from kaleta.models.user import User
from kaleta.services.auth_service import AuthService
from kaleta.services.data_encryption_service import DataEncryptionService
from kaleta.services.local_identity_service import (
    LocalIdentityService,
    identity_id_of,
    normalise_email,
    subject_of,
)
from kaleta.services.tenant_service import (
    TenantMembership,
    TenantService,
    clear_member_keys,
    invite_token_hash,
)

log = logging.getLogger(__name__)

#: How long an invitation link stays good (the plan's 72 hours).
INVITE_TTL = timedelta(hours=72)
_TOKEN_BYTES = 32
DISPLAY_NAME_MAX = 100


@dataclass(frozen=True)
class HouseholdMember:
    """One row of Settings → Household: what members may see of each other."""

    member_id: int
    email: str
    display_name: str
    role: TenantRole
    status: TenantMemberStatus
    joined_at: datetime | None
    #: Of the member's public key; ``None`` before they set a passphrase.
    fingerprint: str | None
    #: A keypair is set up — what approving seals the key to.
    has_keys: bool


@dataclass(frozen=True)
class PendingInvitation:
    email: str
    role: TenantRole
    expires_at: datetime


@dataclass(frozen=True)
class Invitation:
    """A new invitation. ``token`` is shown once, inside the link; only its hash is kept."""

    token: str
    email: str
    expires_at: datetime

    def link(self, base_url: str) -> str:
        return f"{base_url.rstrip('/')}/join?token={self.token}"


@dataclass(frozen=True)
class RemovedMember:
    """Who lost access — for the caller to drop what its process holds for them."""

    tenant_id: int
    user_id: int
    #: The household was re-keyed (``False``: removed without re-keying).
    rekeyed: bool


def next_key_version(version: int) -> int:
    """1 … 255 and round again: the header has one byte, and only old ≠ new matters."""
    return version % 255 + 1


class HouseholdRekey:
    """Move a household's data to a new key while a member leaves it.

    One transaction on the family's session (it reaches ``public`` too): every
    encrypted column read under the old key and written under the new one,
    every blind index recomputed, the new key sealed to each remaining member,
    the leaving member marked ``removed`` and their sessions revoked, and
    ``tenants.key_version`` bumped. A crash rolls all of it back — nothing is
    ever half re-keyed — and the tenant's ``rekeying`` mark is cleared at the
    next start (``release_interrupted_rekeys``).

    Around it, the family is *frozen* in the key ring: its unlocks read as
    locked and new ones are refused, so nothing new is written under the old
    key. A write that bound its parameters before the freeze may still land
    after the pass; the sweep after the commit rewrites any row left under the
    old version, while the old key is still in hand.
    """

    def __init__(
        self,
        public: AsyncSession,
        tenant_session: Callable[[], AsyncSession],
    ) -> None:
        self.public = public
        self.tenant_session = tenant_session

    async def run(self, tenant: Tenant, old: DataKey, leaving: TenantMember) -> DataKey:
        if old.version != tenant.key_version:
            msg = "The unlocked key is not the household's current one. Sign in again."
            raise ConflictError(msg)
        remaining = await self._remaining_holders(tenant.id, leaving.id)
        new = DataKey(generate_dek(), version=next_key_version(old.version))
        ctx = TenantContext(tenant_id=tenant.id, schema=tenant.schema_name)
        key_ring.freeze(tenant.id)
        committed = False
        try:
            await self._mark(tenant.id, TenantStatus.REKEYING)
            with use_tenant(ctx), use_data_key(new), also_read_under(old):
                async with self.tenant_session() as session:
                    counts = await DataEncryptionService(session).rewrite_all()
                    for member_id, public_key in remaining:
                        await session.execute(
                            update(TenantMember)
                            .where(TenantMember.id == member_id)
                            .values(dek_sealed=seal(new.dek, public_key))
                        )
                    await session.execute(_removal(leaving.id))
                    if leaving.user_id is not None:
                        await AuthService(session).revoke_sessions(leaving.user_id, commit=False)
                    await session.execute(
                        update(Tenant)
                        .where(Tenant.id == tenant.id)
                        .values(key_version=new.version, status=TenantStatus.ACTIVE)
                    )
                    await session.commit()
            committed = True
            if leaving.user_id is not None:
                key_ring.lock_member(tenant_member_ref(tenant.id, leaving.user_id))
            key_ring.replace_data_key(tenant.id, new)
            stragglers = await self._sweep(ctx, old, new)
            log.info(
                "Re-keyed tenant %s to key version %d: %d rows, %d stragglers",
                tenant.id,
                new.version,
                sum(counts.values()),
                stragglers,
            )
            return new
        finally:
            if not committed:
                await self._mark(tenant.id, TenantStatus.ACTIVE)
            key_ring.thaw(tenant.id)

    async def _remaining_holders(self, tenant_id: int, leaving_id: int) -> list[tuple[int, bytes]]:
        result = await self.public.execute(
            select(TenantMember.id, TenantMember.public_key).where(
                TenantMember.tenant_id == tenant_id,
                TenantMember.id != leaving_id,
                TenantMember.status == TenantMemberStatus.ACTIVE,
            )
        )
        holders: list[tuple[int, bytes]] = []
        for member_id, public_key in result.all():
            if public_key is None:
                msg = "A member of this household has no key set up to seal the new one to."
                raise ConflictError(msg)
            holders.append((member_id, public_key))
        return holders

    async def _sweep(self, ctx: TenantContext, old: DataKey, new: DataKey) -> int:
        with use_tenant(ctx), use_data_key(new), also_read_under(old):
            async with self.tenant_session() as session:
                counts = await DataEncryptionService(session).rewrite_all(
                    only_key_version=old.version
                )
                await session.commit()
        return sum(counts.values())

    async def _mark(self, tenant_id: int, status: TenantStatus) -> None:
        await self.public.execute(
            update(Tenant).where(Tenant.id == tenant_id).values(status=status)
        )
        await self.public.commit()


def _removal(member_id: int) -> Update:
    """A member out: ``removed``, no sealed key, never the owner."""
    return (
        update(TenantMember)
        .where(TenantMember.id == member_id)
        .values(
            status=TenantMemberStatus.REMOVED,
            removed_at=datetime.now(UTC),
            dek_sealed=None,
            role=TenantRole.MEMBER,
        )
    )


class HouseholdService:
    """``me`` acting in their own household."""

    def __init__(
        self,
        public: AsyncSession,
        me: TenantMembership,
        *,
        tenant_session: Callable[[], AsyncSession] | None = None,
        max_members: int | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.public = public
        self.me = me
        self._tenant_session = tenant_session
        self.max_members = (
            max_members if max_members is not None else settings.household_max_members
        )
        self._clock = clock or (lambda: datetime.now(UTC))

    @classmethod
    async def for_subject(
        cls,
        public: AsyncSession,
        subject: str,
        *,
        tenant_session: Callable[[], AsyncSession] | None = None,
        max_members: int | None = None,
    ) -> HouseholdService:
        membership = await TenantService(public).get_member_by_subject(subject)
        if membership is None or membership.member.status is TenantMemberStatus.REMOVED:
            msg = "You are not a member of a household."
            raise NotFoundError(msg)
        return cls(public, membership, tenant_session=tenant_session, max_members=max_members)

    @property
    def tenant(self) -> Tenant:
        return self.me.tenant

    @property
    def is_owner(self) -> bool:
        return self.me.member.role is TenantRole.OWNER

    # ── Reads ────────────────────────────────────────────────────────────────

    async def members(self) -> list[HouseholdMember]:
        """Everyone who is or is becoming a member; removed ones are left out."""
        self._require_active()
        rows = await self._member_rows()
        names = await self._display_names([m.user_id for m in rows if m.user_id is not None])
        return [
            HouseholdMember(
                member_id=m.id,
                email=m.email,
                display_name=names.get(m.user_id or 0) or m.email.split("@", 1)[0],
                role=m.role,
                status=m.status,
                joined_at=m.joined_at,
                fingerprint=fingerprint(m.public_key) if m.public_key is not None else None,
                has_keys=m.public_key is not None,
            )
            for m in rows
        ]

    async def invitations(self) -> list[PendingInvitation]:
        self._require_active()
        result = await self.public.execute(
            select(TenantInvite)
            .where(
                TenantInvite.tenant_id == self.tenant.id,
                TenantInvite.accepted_at.is_(None),
                TenantInvite.expires_at > self._clock(),
            )
            .order_by(TenantInvite.expires_at)
        )
        return [
            PendingInvitation(email=i.email, role=i.role, expires_at=i.expires_at)
            for i in result.scalars().all()
        ]

    # ── The owner's ──────────────────────────────────────────────────────────

    async def invite(self, email: str) -> Invitation:
        """A link for ``email`` to join as a member; replaces an earlier open one."""
        self._require_owner()
        address = normalise_email(email)
        local, _, domain = address.partition("@")
        if not local or not domain or "@" in domain or any(c.isspace() for c in address):
            msg = "Enter an e-mail address."
            raise ValidationError(msg)
        existing = (
            await self.public.execute(select(TenantMember).where(TenantMember.email == address))
        ).scalar_one_or_none()
        if existing is not None:
            if existing.tenant_id != self.tenant.id:
                msg = "This e-mail address already belongs to another account."
                raise ConflictError(msg)
            if existing.status is not TenantMemberStatus.REMOVED:
                msg = "This person is already a member of your household."
                raise ConflictError(msg)
        await self.public.execute(
            delete(TenantInvite).where(
                TenantInvite.tenant_id == self.tenant.id,
                TenantInvite.email == address,
                TenantInvite.accepted_at.is_(None),
            )
        )
        if await self._places_taken() >= self.max_members:
            msg = f"A household has at most {self.max_members} members, invitations included."
            raise ConflictError(msg)
        token = secrets.token_urlsafe(_TOKEN_BYTES)
        expires = self._clock() + INVITE_TTL
        self.public.add(
            TenantInvite(
                token_hash=invite_token_hash(token),
                tenant_id=self.tenant.id,
                email=address,
                role=TenantRole.MEMBER,
                expires_at=expires,
            )
        )
        await self.public.commit()
        log.info("Tenant %s invited a member", self.tenant.id)
        return Invitation(token=token, email=address, expires_at=expires)

    async def cancel_invitation(self, email: str) -> None:
        self._require_owner()
        await self.public.execute(
            delete(TenantInvite).where(
                TenantInvite.tenant_id == self.tenant.id,
                TenantInvite.email == normalise_email(email),
                TenantInvite.accepted_at.is_(None),
            )
        )
        await self.public.commit()

    async def approve(self, member_id: int, data_key: DataKey | None) -> None:
        """Seal the household's key to a pending member's keypair; they are in."""
        self._require_owner()
        member = await self._member(member_id)
        if member.status is not TenantMemberStatus.PENDING:
            msg = "Only a member waiting for approval can be approved."
            raise ConflictError(msg)
        if settings.encryption_enabled:
            key = self._require_key(data_key)
            if member.public_key is None:
                msg = "This member has not set up their data passphrase yet."
                raise ConflictError(msg)
            member.dek_sealed = seal(key.dek, member.public_key)
        member.status = TenantMemberStatus.ACTIVE
        member.joined_at = self._clock()
        await self.public.commit()
        log.info("Tenant %s approved member %s", self.tenant.id, member.id)

    async def decline(self, member_id: int) -> None:
        """Turn a pending member away: their membership goes, and a login the invitation made."""
        self._require_owner()
        member = await self._member(member_id)
        if member.status is not TenantMemberStatus.PENDING:
            msg = "Only a member waiting for approval can be declined."
            raise ConflictError(msg)
        subject = member.auth_subject
        await self.public.delete(member)
        await self.public.commit()
        await self._delete_invited_login(subject)
        log.info("Tenant %s declined member %s", self.tenant.id, member_id)

    async def remove(
        self, member_id: int, data_key: DataKey | None, *, rekey: bool = True
    ) -> RemovedMember:
        """Take an active member out; by default re-key so their old key opens nothing new."""
        self._require_owner()
        member = await self._member(member_id)
        if member.id == self.me.member.id:
            msg = "Hand the household to another member before you leave it."
            raise ConflictError(msg)
        if member.status is not TenantMemberStatus.ACTIVE:
            msg = "Only an active member can be removed; decline a pending one."
            raise ConflictError(msg)
        return await self._take_out(member, data_key, rekey=rekey)

    async def transfer_ownership(self, member_id: int) -> None:
        """Make another active member the owner; ``me`` becomes a member."""
        self._require_owner()
        member = await self._member(member_id)
        if member.id == self.me.member.id:
            msg = "You are the owner already."
            raise ConflictError(msg)
        if member.status is not TenantMemberStatus.ACTIVE:
            msg = "Only an active member can become the owner."
            raise ConflictError(msg)
        self.me.member.role = TenantRole.MEMBER
        member.role = TenantRole.OWNER
        await self.public.commit()
        log.info("Tenant %s: ownership moved to member %s", self.tenant.id, member.id)

    # ── Every member's own ───────────────────────────────────────────────────

    async def leave(self, data_key: DataKey | None, *, rekey: bool = True) -> RemovedMember:
        self._require_active()
        if self.is_owner:
            msg = "Hand the household to another member before you leave it."
            raise ConflictError(msg)
        return await self._take_out(self.me.member, data_key, rekey=rekey)

    async def reset_keys(self) -> None:
        """Lost both passphrase and recovery code: start over as ``pending``.

        The household's data stays sealed to the others; the member sets a new
        passphrase and the owner approves the new keypair.
        """
        member = self.me.member
        if member.status is TenantMemberStatus.REMOVED:
            msg = "You are not a member of this household."
            raise ConflictError(msg)
        if self.is_owner:
            msg = "The owner's key cannot be reset: the household would lose its data."
            raise ConflictError(msg)
        clear_member_keys(member)
        member.status = TenantMemberStatus.PENDING
        await self.public.commit()
        if member.user_id is not None:
            key_ring.lock_member(tenant_member_ref(self.tenant.id, member.user_id))

    async def set_display_name(self, name: str) -> None:
        """What the household sees ``me`` as — the member's own to choose."""
        cleaned = " ".join(name.split())
        if not cleaned:
            msg = "Enter a name."
            raise ValidationError(msg)
        if len(cleaned) > DISPLAY_NAME_MAX:
            msg = f"Keep the name under {DISPLAY_NAME_MAX} characters."
            raise ValidationError(msg)
        user_id = self.me.member.user_id
        if user_id is None:
            raise NotFoundError("Your account is still being set up.")
        with use_tenant(self._context()):
            async with self._session_factory()() as session:
                await session.execute(
                    update(User).where(User.id == user_id).values(display_name=cleaned)
                )
                await session.commit()

    # ── Helpers ──────────────────────────────────────────────────────────────

    async def _take_out(
        self, member: TenantMember, data_key: DataKey | None, *, rekey: bool
    ) -> RemovedMember:
        if member.user_id is None:
            msg = "This member has no account in the household yet."
            raise ConflictError(msg)
        user_id = member.user_id
        if settings.encryption_enabled and rekey:
            key = self._require_key(data_key)
            tenant = await self.public.get(Tenant, self.tenant.id, populate_existing=True)
            if tenant is None:
                raise NotFoundError("This household is gone.")
            await HouseholdRekey(self.public, self._session_factory()).run(tenant, key, member)
            await self.public.refresh(member)
        else:
            await self.public.execute(_removal(member.id))
            await self.public.commit()
            with use_tenant(self._context()):
                async with self._session_factory()() as session:
                    await AuthService(session).revoke_sessions(user_id)
            key_ring.lock_member(tenant_member_ref(self.tenant.id, user_id))
        log.info("Tenant %s: member %s removed (re-key: %s)", self.tenant.id, member.id, rekey)
        return RemovedMember(tenant_id=self.tenant.id, user_id=user_id, rekeyed=rekey)

    async def _member_rows(self) -> list[TenantMember]:
        result = await self.public.execute(
            select(TenantMember)
            .where(
                TenantMember.tenant_id == self.tenant.id,
                TenantMember.status != TenantMemberStatus.REMOVED,
            )
            .order_by(TenantMember.role, TenantMember.id)
        )
        return list(result.scalars().all())

    async def _member(self, member_id: int) -> TenantMember:
        member = await self.public.get(TenantMember, member_id)
        if member is None or member.tenant_id != self.tenant.id:
            raise NotFoundError("No such member in your household.")
        return member

    async def _places_taken(self) -> int:
        members = await self.public.scalar(
            select(func.count(TenantMember.id)).where(
                TenantMember.tenant_id == self.tenant.id,
                TenantMember.status != TenantMemberStatus.REMOVED,
            )
        )
        invites = await self.public.scalar(
            select(func.count(TenantInvite.id)).where(
                TenantInvite.tenant_id == self.tenant.id,
                TenantInvite.accepted_at.is_(None),
                TenantInvite.expires_at > self._clock(),
            )
        )
        return int(members or 0) + int(invites or 0)

    async def _display_names(self, user_ids: list[int]) -> dict[int, str]:
        if not user_ids:
            return {}
        with use_tenant(self._context()):
            async with self._session_factory()() as session:
                result = await session.execute(
                    select(User.id, User.display_name).where(User.id.in_(user_ids))
                )
                return {uid: name for uid, name in result.all() if name}

    async def _delete_invited_login(self, subject: str) -> None:
        """The ``local`` login an invitation created, unless it is the administrator's."""
        identity_id = identity_id_of(subject)
        if identity_id is None:
            return
        logins = LocalIdentityService(self.public)
        login = await logins.get(identity_id)
        if login is not None and not login.is_instance_admin:
            await logins.delete(identity_id)

    def _require_active(self) -> None:
        if self.me.member.status is not TenantMemberStatus.ACTIVE:
            msg = "Your membership is waiting for the owner's approval."
            raise UnauthorizedError(msg)

    def _require_owner(self) -> None:
        self._require_active()
        if not self.is_owner:
            msg = "Only the household's owner can do this."
            raise UnauthorizedError(msg)

    @staticmethod
    def _require_key(data_key: DataKey | None) -> DataKey:
        if data_key is None:
            raise TenantLockedError("Unlock your data with your passphrase first.")
        return data_key

    def _context(self) -> TenantContext:
        return TenantContext(tenant_id=self.tenant.id, schema=self.tenant.schema_name)

    def _session_factory(self) -> Callable[[], AsyncSession]:
        if self._tenant_session is None:
            from kaleta.db import AsyncSessionFactory

            self._tenant_session = AsyncSessionFactory
        return self._tenant_session


@dataclass(frozen=True)
class InvitationPreview:
    """What ``/join`` shows before anyone signs in: the address, and when it expires."""

    email: str
    expires_at: datetime


class HouseholdInvitations:
    """What an invitation link may do, with nobody signed in."""

    def __init__(
        self,
        public: AsyncSession,
        *,
        tenant_session: Callable[[], AsyncSession] | None = None,
    ) -> None:
        self.public = public
        self._tenants = TenantService(public, tenant_session=tenant_session)

    async def preview(self, token: str) -> InvitationPreview:
        invite = await self._tenants.invitation_by_token(token)
        return InvitationPreview(email=invite.email, expires_at=invite.expires_at)

    async def accept_with_password(self, token: str, password: str) -> str:
        """``local`` logins: the invitee chooses a password; return the new login's e-mail.

        The token is the proof here — a local address is never verified — so
        the login is created for the invited address and nothing else. The
        caller then signs in with it as usual, and the member is ``pending``.
        """
        invite = await self._tenants.invitation_by_token(token)
        logins = LocalIdentityService(self.public)
        if await logins.get_by_email(invite.email) is not None:
            msg = "This e-mail address already has a login here. Sign in with it to accept."
            raise ConflictError(msg)
        login = await logins.create(invite.email, password)
        try:
            await self._tenants.join(invite, subject=subject_of(login.id))
        except Exception:
            await self.public.rollback()
            await logins.delete(login.id)
            raise
        return login.email
