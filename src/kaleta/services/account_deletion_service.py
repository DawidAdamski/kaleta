# SPDX-License-Identifier: AGPL-3.0-or-later
"""Deleting a hosted account: its members' identities, its schema, its registry rows.

``KALETA_TENANCY=multi`` only. Two callers: ``scripts/tenant_admin.py delete``
(the operator) and Settings → Data → "Delete my account" (the owner — the GDPR
path). Both go through here so the order is the same:

1. every member's identity is removed at the provider (Supabase Auth with the
   service-role key), so nobody can sign in to what is about to vanish;
2. then the schema is dropped and the registry rows deleted.

A provider that fails in step 1 stops the run before any data is dropped, so a
retry finds the account whole; an identity that is already gone is not an
error to the provider. Works on a *public* session, like ``TenantService``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import NotFoundError
from kaleta.models.tenant import TenantMember, TenantMemberStatus, TenantRole
from kaleta.services.tenant_service import TenantService

logger = logging.getLogger(__name__)


class IdentityRemover(Protocol):
    """The one ``AuthProvider`` call deletion needs."""

    async def delete_identity(self, subject: str) -> None: ...


@dataclass(frozen=True)
class AccountMember:
    """A member as the deletion screens list them: who loses access."""

    email: str
    role: TenantRole
    status: TenantMemberStatus


@dataclass(frozen=True)
class AccountDeletion:
    """What a deletion removed — for the operator's audit line."""

    tenant_id: int
    schema: str
    identities_removed: int


class AccountDeletionService:
    def __init__(
        self,
        session: AsyncSession,
        remover: IdentityRemover,
        *,
        tenant_service: TenantService | None = None,
    ) -> None:
        self.session = session
        self._remover = remover
        self._tenants = tenant_service or TenantService(session)

    async def members(self, tenant_id: int) -> list[AccountMember]:
        """Everyone who belongs to the account and has not left it, owner first."""
        result = await self.session.execute(
            select(TenantMember)
            .where(
                TenantMember.tenant_id == tenant_id,
                TenantMember.status != TenantMemberStatus.REMOVED,
            )
            .order_by(TenantMember.id)
        )
        rows = list(result.scalars().all())
        rows.sort(key=lambda m: m.role is not TenantRole.OWNER)
        return [AccountMember(email=m.email, role=m.role, status=m.status) for m in rows]

    async def is_owner(self, tenant_id: int, auth_subject: str) -> bool:
        membership = await self._tenants.get_member_by_subject(auth_subject)
        return (
            membership is not None
            and membership.tenant.id == tenant_id
            and membership.member.role is TenantRole.OWNER
            and membership.member.status is TenantMemberStatus.ACTIVE
        )

    async def delete(self, tenant_id: int) -> AccountDeletion:
        """Remove every member's identity, then the account's schema and rows.

        Raises ``NotFoundError`` for an unknown tenant and whatever the provider
        raises (``ExternalServiceError``, ``ValidationError``) when an identity
        cannot be removed — in which case nothing has been dropped yet.
        """
        tenant = await self._tenants.get_tenant(tenant_id)
        if tenant is None:
            msg = f"Tenant {tenant_id} not found"
            raise NotFoundError(msg)
        schema = tenant.schema_name
        result = await self.session.execute(
            select(TenantMember.auth_subject).where(TenantMember.tenant_id == tenant_id)
        )
        subjects = list(result.scalars().all())
        for subject in subjects:
            await self._remover.delete_identity(subject)
        await self._tenants.delete(tenant_id)
        logger.info(
            "Deleted tenant %s (schema %s, %d identities)", tenant_id, schema, len(subjects)
        )
        return AccountDeletion(tenant_id=tenant_id, schema=schema, identities_removed=len(subjects))
