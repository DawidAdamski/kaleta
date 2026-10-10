# SPDX-License-Identifier: AGPL-3.0-or-later
"""The tenant registry: who belongs to which account, and making accounts.

Every instance keeps one (ADR-35, ADR-38). Works on a *public* session — the
registry lives in ``public`` — and reaches into a tenant schema only to create
it and to write the owner's ``users`` row.

Provisioning happens at an identity's first verified sign-in: a new schema
named ``t_`` + 12 random hex characters, brought to the tenant head by
``alembic/`` with ``-x tenant_schema=``, then the owner's ``users`` row. It is
idempotent and serialised per identity, so a double-submitted login creates
one schema, not two.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import ClassVar, Protocol

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from kaleta.db.tenant_context import TenantContext, use_tenant
from kaleta.db.tenant_schemas import new_schema_name, quote_schema
from kaleta.exceptions import ConflictError, NotFoundError, UnauthorizedError
from kaleta.models.tenant import (
    Tenant,
    TenantMember,
    TenantMemberStatus,
    TenantRole,
    TenantStatus,
)
from kaleta.models.user import User
from kaleta.schemas.identity import Identity

logger = logging.getLogger(__name__)

#: ``users.display_name`` length; it starts out as the e-mail's local part.
_DISPLAY_NAME_MAX = 100


class SchemaProvisioner(Protocol):
    """Creates a tenant schema and brings it to the tenant head."""

    async def create(self, schema: str) -> None: ...

    async def drop(self, schema: str) -> None: ...

    async def pending(self, schema: str) -> bool: ...


class AlembicSchemaProvisioner:
    """``CREATE SCHEMA`` plus ``alembic upgrade head``."""

    def __init__(self, db_url: str, session_factory: Callable[[], AsyncSession]) -> None:
        self._db_url = db_url
        self._public = session_factory

    async def create(self, schema: str) -> None:
        from kaleta.services.setup_service import upgrade_to_head

        async with self._public() as session:
            await session.execute(text(f"CREATE SCHEMA IF NOT EXISTS {quote_schema(schema)}"))
            await session.commit()
        # Alembic's API is synchronous and runs its own event loop.
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: upgrade_to_head(self._db_url, schema=schema))

    async def drop(self, schema: str) -> None:
        async with self._public() as session:
            await session.execute(text(f"DROP SCHEMA IF EXISTS {quote_schema(schema)} CASCADE"))
            await session.commit()

    async def pending(self, schema: str) -> bool:
        from kaleta.services.setup_service import current_revision, head_revision

        loop = asyncio.get_running_loop()
        current = await loop.run_in_executor(
            None, lambda: current_revision(self._db_url, schema=schema)
        )
        return current != head_revision()


@dataclass(frozen=True)
class TenantMembership:
    """A member row together with the tenant it belongs to."""

    member: TenantMember
    tenant: Tenant

    def context(self) -> TenantContext:
        return TenantContext(
            tenant_id=self.tenant.id,
            schema=self.tenant.schema_name,
            member_user_id=self.member.user_id,
        )


class TenantService:
    """Registry reads and writes, on a session with no tenant schema."""

    #: One lock per identity within this process; Postgres adds an advisory
    #: lock for the other replicas.
    _local_locks: ClassVar[dict[str, asyncio.Lock]] = {}

    def __init__(
        self,
        session: AsyncSession,
        *,
        provisioner: SchemaProvisioner | None = None,
        tenant_session: Callable[[], AsyncSession] | None = None,
    ) -> None:
        self.session = session
        self._provisioner = provisioner
        self._tenant_session = tenant_session

    # ── Reads ────────────────────────────────────────────────────────────────

    async def get_member_by_subject(self, subject: str) -> TenantMembership | None:
        result = await self.session.execute(
            select(TenantMember, Tenant)
            .join(Tenant, Tenant.id == TenantMember.tenant_id)
            .where(TenantMember.auth_subject == subject)
        )
        row = result.one_or_none()
        if row is None:
            return None
        return TenantMembership(member=row[0], tenant=row[1])

    async def get_tenant(self, tenant_id: int) -> Tenant | None:
        return await self.session.get(Tenant, tenant_id)

    async def list_tenants(self) -> list[Tenant]:
        result = await self.session.execute(select(Tenant).order_by(Tenant.id))
        return list(result.scalars().all())

    # ── Provisioning ─────────────────────────────────────────────────────────

    async def provision(self, identity: Identity) -> Tenant:
        """The tenant ``identity`` owns, creating it on first call.

        Only a verified identity gets an account: provisioning at first
        verified sign-in rather than at sign-up keeps bots that never confirm
        an e-mail from leaving schemas behind.
        """
        if not identity.email_verified:
            msg = "Confirm your e-mail address before signing in."
            raise UnauthorizedError(msg)
        async with self._provision_lock(identity.subject):
            existing = await self.get_member_by_subject(identity.subject)
            if existing is not None and existing.tenant.status is not TenantStatus.PROVISIONING:
                return existing.tenant
            if existing is None:
                email = identity.email.strip().lower()
                taken = await self.session.execute(
                    select(TenantMember.id).where(TenantMember.email == email)
                )
                if taken.scalar_one_or_none() is not None:
                    msg = "This e-mail address already belongs to another account."
                    raise ConflictError(msg)
                tenant = Tenant(
                    schema_name=new_schema_name(), status=TenantStatus.PROVISIONING, key_version=1
                )
                self.session.add(tenant)
                await self.session.flush()
                member = TenantMember(
                    tenant_id=tenant.id,
                    auth_subject=identity.subject,
                    email=email,
                    role=TenantRole.OWNER,
                    status=TenantMemberStatus.PENDING,
                )
                self.session.add(member)
                # Committed before the schema exists, so a crash below leaves a
                # `provisioning` row the next sign-in resumes, not an orphan.
                await self.session.commit()
            else:
                tenant, member = existing.tenant, existing.member
            await self._build_schema(tenant, member)
            return tenant

    async def _build_schema(self, tenant: Tenant, member: TenantMember) -> None:
        provisioner = self._require_provisioner()
        await provisioner.create(tenant.schema_name)
        ctx = TenantContext(tenant_id=tenant.id, schema=tenant.schema_name)
        user_id = await self._ensure_owner_user(ctx, member)
        now = datetime.now(UTC)
        member.user_id = user_id
        member.status = TenantMemberStatus.ACTIVE
        member.joined_at = member.joined_at or now
        tenant.status = TenantStatus.ACTIVE
        tenant.last_seen_at = now
        await self.session.commit()
        logger.info("Provisioned tenant %s (schema %s)", tenant.id, tenant.schema_name)

    async def _ensure_owner_user(self, ctx: TenantContext, member: TenantMember) -> int:
        """The owner's ``users`` row in the new schema — found again on a resumed run."""
        with use_tenant(ctx):
            tenant_session = self._require_tenant_session()()
        async with tenant_session as session:
            result = await session.execute(select(User).where(User.username == member.email))
            user = result.scalar_one_or_none()
            if user is None:
                user = User(
                    username=member.email,
                    email=member.email,
                    display_name=member.email.split("@", 1)[0][:_DISPLAY_NAME_MAX],
                    password_hash=None,
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
            return user.id

    @asynccontextmanager
    async def _provision_lock(self, subject: str) -> AsyncIterator[None]:
        # Never removed: a lock dropped while a waiter still holds it would let
        # the next caller in beside that waiter. One small object per identity
        # that signed in during this process's life.
        lock = self._local_locks.setdefault(subject, asyncio.Lock())
        async with lock:
            bind = self.session.bind
            if bind is None:
                yield
                return
            digest = hashlib.sha256(subject.encode()).digest()[:8]
            key = int.from_bytes(digest, "big", signed=True)
            # Session-level, not transaction-level, and on a connection of its
            # own: provisioning commits several times while the lock must stay
            # held, and every commit hands the session's connection back.
            engine = bind if isinstance(bind, AsyncEngine) else bind.engine
            async with engine.connect() as lock_conn:
                await lock_conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": key})
                try:
                    yield
                finally:
                    await lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})

    # ── Sign-in bookkeeping ──────────────────────────────────────────────────

    async def membership_for_sign_in(self, identity: Identity) -> TenantMembership:
        """Provision if needed, refuse a closed account, keep the e-mail in step."""
        tenant = await self.provision(identity)
        membership = await self.get_member_by_subject(identity.subject)
        if membership is None or membership.tenant.id != tenant.id:
            msg = "Account registry changed during sign-in; try again."
            raise ConflictError(msg)
        if membership.tenant.status is not TenantStatus.ACTIVE:
            msg = "This account is not available."
            raise UnauthorizedError(msg)
        if membership.member.status is not TenantMemberStatus.ACTIVE:
            msg = "Your membership of this account is not active."
            raise UnauthorizedError(msg)
        await self._sync_email(membership, identity.email)
        return membership

    async def _sync_email(self, membership: TenantMembership, email: str) -> None:
        """An e-mail changed at the provider changes the registry and ``users`` row."""
        email = email.strip().lower()
        member = membership.member
        if not email or member.email == email:
            return
        member.email = email
        await self.session.commit()
        if member.user_id is None:
            return
        with use_tenant(membership.context()):
            tenant_session = self._require_tenant_session()()
        async with tenant_session as session:
            user = await session.get(User, member.user_id)
            if user is not None:
                user.email = email
                user.username = email
                await session.commit()

    async def mark_seen(self, tenant_id: int) -> None:
        tenant = await self._require_tenant(tenant_id)
        tenant.last_seen_at = datetime.now(UTC)
        await self.session.commit()

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def suspend(self, tenant_id: int) -> Tenant:
        tenant = await self._require_tenant(tenant_id)
        tenant.status = TenantStatus.SUSPENDED
        await self.session.commit()
        return tenant

    async def resume(self, tenant_id: int) -> Tenant:
        """A suspended account is let in again; any other status is left alone."""
        tenant = await self._require_tenant(tenant_id)
        if tenant.status is not TenantStatus.SUSPENDED:
            msg = f"Tenant {tenant_id} is {tenant.status.value}, not suspended."
            raise ConflictError(msg)
        tenant.status = TenantStatus.ACTIVE
        await self.session.commit()
        return tenant

    async def delete(self, tenant_id: int) -> list[str]:
        """Drop the tenant's schema and registry rows; return its members' subjects.

        The caller removes those identities at the provider — this layer does
        not talk to Supabase.
        """
        tenant = await self._require_tenant(tenant_id)
        tenant.status = TenantStatus.DELETING
        await self.session.commit()
        members = await self.session.execute(
            select(TenantMember.auth_subject).where(TenantMember.tenant_id == tenant_id)
        )
        subjects = list(members.scalars().all())
        await self._require_provisioner().drop(tenant.schema_name)
        await self.session.delete(tenant)
        await self.session.commit()
        return subjects

    async def tenants_pending_migration(self) -> list[Tenant]:
        provisioner = self._require_provisioner()
        return [t for t in await self.list_tenants() if await provisioner.pending(t.schema_name)]

    # ── Helpers ──────────────────────────────────────────────────────────────

    async def _require_tenant(self, tenant_id: int) -> Tenant:
        tenant = await self.get_tenant(tenant_id)
        if tenant is None:
            msg = f"Tenant {tenant_id} not found"
            raise NotFoundError(msg)
        return tenant

    def _require_provisioner(self) -> SchemaProvisioner:
        if self._provisioner is None:
            from kaleta.config import settings
            from kaleta.db import AsyncSessionFactory

            self._provisioner = AlembicSchemaProvisioner(
                settings.db_url, AsyncSessionFactory.public
            )
        return self._provisioner

    def _require_tenant_session(self) -> Callable[[], AsyncSession]:
        if self._tenant_session is None:
            from kaleta.db import AsyncSessionFactory

            self._tenant_session = AsyncSessionFactory
        return self._tenant_session
