# SPDX-License-Identifier: AGPL-3.0-or-later
"""From "the provider accepted this identity" to "this is the session to open".

Kept out of the views so the login page, the sign-up page and the tests all go
through one path. The identity is looked up in the registry — provisioned on
its first verified sign-in — and the session is opened for that family's
schema, as that member's ``users`` row.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from kaleta.auth.login_rate_limit import resend_throttle
from kaleta.auth.providers import RegistryAuthProvider, get_auth_provider
from kaleta.auth.session import SessionTenant
from kaleta.db import AsyncSessionFactory
from kaleta.db.tenant_context import use_tenant
from kaleta.exceptions import UnauthorizedError
from kaleta.schemas.identity import Identity, MfaRequired, RegistrationMode
from kaleta.services import AuthService, HostedMfaService, MfaService, TenantService
from kaleta.services.local_identity_service import LocalIdentityService
from kaleta.services.mfa_service import normalise_code

if TYPE_CHECKING:
    from kaleta.services.tenant_service import TenantMembership

#: Where a sign-in lands while the account owes a new second factor.
MFA_REENROL_TARGET = "/settings?tab=security"


@dataclass(frozen=True)
class SignedIn:
    """Everything ``finish_login`` needs."""

    user_id: int
    username: str
    tenant: SessionTenant | None = None
    #: A recovery code spent the provider's factor and none has been set up
    #: since: the login goes to Settings → Security instead of its target.
    reenrol_mfa: bool = False

    def target(self, requested: str) -> str:
        return MFA_REENROL_TARGET if self.reenrol_mfa else requested


class SignInFlow:
    def __init__(self, tenant_service: TenantService | None = None) -> None:
        # Injected by tests; otherwise one per call on a fresh public session.
        self._tenant_service = tenant_service

    async def complete(self, identity: Identity) -> SignedIn:
        signed_in = await self._complete_in_family(identity)
        # Kaleta's session is the session of record; nothing keeps the
        # provider's, so end it rather than leave a refresh token behind.
        await get_auth_provider().sign_out(identity)
        return signed_in

    async def verify_code(self, pending: MfaRequired, code: str) -> SignedIn:
        """Finish a hosted sign-in with the authenticator's code.

        The provider checks the code and lifts the session to ``aal2`` — the
        one place that claim is enforced (see the plan's Implementation
        notes): Kaleta's own session is the session of record afterwards, and
        the provider's is ended in :meth:`complete`. A wrong code is a
        ``ValidationError``; a factor removed meanwhile a ``ConflictError``.
        """
        lifted = await get_auth_provider().mfa_challenge_verify(
            pending.identity, pending.factor_id, normalise_code(code)
        )
        return await self.complete(lifted)

    async def recover(self, pending: MfaRequired, code: str) -> SignedIn | None:
        """Finish a hosted sign-in with a recovery code instead of the authenticator.

        ``None`` when the code is not one of this account's unused codes. On a
        right one the provider's factor is removed (``HostedMfaService``) and
        the sign-in completes — on to Settings → Security, to set a new one up.
        """
        identity = pending.identity
        provider = get_auth_provider()
        if isinstance(provider, RegistryAuthProvider):
            # A local factor: the code is crossed off in `user_mfa`, and the
            # factor stays.
            if not await provider.consume_recovery_code(identity, code):
                return None
            return await self.complete(identity)
        membership = await self._membership(identity)
        user_id = self._member_user_id(membership)
        with use_tenant(membership.context()):
            async with AsyncSessionFactory() as session:
                recovered = await HostedMfaService(session, get_auth_provider()).recover(
                    user_id, code, subject=identity.subject, factor_id=pending.factor_id
                )
        if not recovered:
            return None
        return await self.complete(identity)

    async def _membership(self, identity: Identity) -> TenantMembership:
        if self._tenant_service is not None:
            return await self._tenant_service.membership_for_sign_in(identity)
        async with AsyncSessionFactory.public() as public:
            return await TenantService(public).membership_for_sign_in(identity)

    @staticmethod
    def _member_user_id(membership: TenantMembership) -> int:
        if membership.member.user_id is None:
            msg = "Your account is still being set up. Try again in a moment."
            raise UnauthorizedError(msg)
        return membership.member.user_id

    async def _complete_in_family(self, identity: Identity) -> SignedIn:
        membership = await self._membership(identity)
        user_id = self._member_user_id(membership)
        ctx = membership.context()
        with use_tenant(ctx):
            async with AsyncSessionFactory() as session:
                await AuthService(session).record_login(username=identity.email, success=True)
                reenrol = await MfaService(session).reenrolment_required(user_id)
        return SignedIn(
            reenrol_mfa=reenrol,
            user_id=user_id,
            username=identity.email,
            tenant=SessionTenant(
                tenant_id=membership.tenant.id,
                schema=membership.tenant.schema_name,
                auth_subject=identity.subject,
                email=identity.email,
            ),
        )


async def resend_confirmation(address: str) -> None:
    """Resend the sign-up confirmation, at most once a minute per address.

    A throttled press returns exactly like a sent one, so the page can say "a
    new link is on its way" either way: neither the throttle nor the provider
    tells anyone whether the address has an account.
    """
    if resend_throttle.allow(address.strip().lower()):
        await get_auth_provider().resend_confirmation(address)


@dataclass(frozen=True)
class SignUpState:
    """What the login and sign-up pages offer on the registry layout."""

    #: No login exists yet: the next sign-up creates the instance administrator.
    first_run: bool
    #: The sign-up page is offered to anyone.
    open: bool


async def registry_sign_up_state() -> SignUpState:
    """Whether this instance is on its first run, and whether sign-up is open.

    Supabase (and the debug ``fake`` backend) always offer sign-up; local
    logins follow the instance's registration mode (ADR-38).
    """
    if not isinstance(get_auth_provider(), RegistryAuthProvider):
        return SignUpState(first_run=False, open=True)
    async with AsyncSessionFactory.public() as session:
        identities = LocalIdentityService(session)
        if await identities.is_empty():
            return SignUpState(first_run=True, open=True)
        mode = await identities.registration_mode()
    return SignUpState(first_run=False, open=mode is RegistrationMode.OPEN)
