# SPDX-License-Identifier: AGPL-3.0-or-later
"""From "the provider accepted this identity" to "this is the session to open".

Kept out of the views so the login page, the sign-up page and the tests all go
through one path. Local mode: the identity's subject is the ``users`` row.
Multi-tenant mode: the identity is looked up in the registry — provisioned on
its first verified sign-in — and the session is opened for that tenant's
schema, as that member's ``users`` row.
"""

from __future__ import annotations

from dataclasses import dataclass

from kaleta.auth.providers import get_auth_provider
from kaleta.auth.session import SessionTenant
from kaleta.config import settings
from kaleta.db import AsyncSessionFactory
from kaleta.db.tenant_context import use_tenant
from kaleta.exceptions import UnauthorizedError
from kaleta.schemas.identity import Identity
from kaleta.services import AuthService, TenantService


@dataclass(frozen=True)
class SignedIn:
    """Everything ``finish_login`` needs."""

    user_id: int
    username: str
    tenant: SessionTenant | None = None


class SignInFlow:
    def __init__(self, tenant_service: TenantService | None = None) -> None:
        # Injected by tests; otherwise one per call on a fresh public session.
        self._tenant_service = tenant_service

    async def complete(self, identity: Identity) -> SignedIn:
        if settings.tenancy != "multi":
            try:
                user_id = int(identity.subject)
            except ValueError as exc:
                msg = "This identity has no account on this install."
                raise UnauthorizedError(msg) from exc
            return SignedIn(user_id=user_id, username=identity.email)
        signed_in = await self._complete_multi(identity)
        # Kaleta's session is the session of record; nothing keeps the
        # provider's, so end it rather than leave a refresh token behind.
        await get_auth_provider().sign_out(identity)
        return signed_in

    async def _complete_multi(self, identity: Identity) -> SignedIn:
        if self._tenant_service is not None:
            membership = await self._tenant_service.membership_for_sign_in(identity)
        else:
            async with AsyncSessionFactory.public() as public:
                membership = await TenantService(public).membership_for_sign_in(identity)
        if membership.member.user_id is None:
            msg = "Your account is still being set up. Try again in a moment."
            raise UnauthorizedError(msg)
        ctx = membership.context()
        with use_tenant(ctx):
            async with AsyncSessionFactory() as session:
                await AuthService(session).record_login(username=identity.email, success=True)
        return SignedIn(
            user_id=membership.member.user_id,
            username=identity.email,
            tenant=SessionTenant(
                tenant_id=membership.tenant.id,
                schema=membership.tenant.schema_name,
                auth_subject=identity.subject,
                email=identity.email,
            ),
        )
