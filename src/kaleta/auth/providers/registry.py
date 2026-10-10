# SPDX-License-Identifier: AGPL-3.0-or-later
"""``KALETA_AUTH_BACKEND=local`` on the registry layout (ADR-38).

Logins are rows of ``public.local_identities`` (``LocalIdentityService``);
the family a login works in is provisioned at its first sign-in by
``TenantService``, exactly as with Supabase, so ``SignInFlow`` cannot tell the
two apart. No e-mail is ever sent: an address is taken as confirmed, the first
sign-up of an empty instance creates its administrator, later sign-ups need
the instance's registration mode to be ``open``, and a forgotten password is
reset by the administrator.

The second factor stays Kaleta's own (``MfaService`` over ``user_mfa`` in the
family's schema). A right password for a member who has one turned on answers
``MfaRequired``; :meth:`mfa_challenge_verify` checks the code inside that
member's family, so the login prompt goes through the same
``SignInFlow.verify_code`` as a hosted sign-in. A factor turned off while the
prompt sat open is a ``ConflictError`` there, as a factor removed at Supabase
is (KAL-AUTH-022): the password is all the login needs now.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from kaleta.db import AsyncSessionFactory
from kaleta.db.tenant_context import use_tenant
from kaleta.exceptions import ConflictError, ValidationError
from kaleta.schemas.identity import FactorEnrolment, Identity, MfaRequired, SignUpResult
from kaleta.services.local_identity_service import LocalIdentityService, identity_id_of
from kaleta.services.mfa_service import MfaService
from kaleta.services.tenant_service import TenantService

if TYPE_CHECKING:
    from kaleta.models.tenant import LocalIdentity
    from kaleta.services.tenant_service import TenantMembership

#: ``MfaRequired.factor_id`` for a factor in ``user_mfa``, not at a provider.
LOCAL_FACTOR = "local"

_ADMIN_RESET = "This instance sends no e-mail; ask its administrator to reset your password."
_NO_MAIL = "This instance sends no e-mail; sign in with your e-mail address and password."
_LOCAL_MFA = "Two-factor authentication is set up in Settings → Security."
_MFA_GONE = "Two-factor authentication was turned off; sign in with your password."
_WRONG_CODE = "That code is not right. Try the current one from your app."


class RegistryAuthProvider:
    name = "local"

    @staticmethod
    def identity_for(row: LocalIdentity) -> Identity:
        return Identity(subject=row.subject, email=row.email, email_verified=True)

    async def sign_up(self, email: str, password: str) -> SignUpResult:
        async with AsyncSessionFactory.public() as session:
            row = await LocalIdentityService(session).sign_up(email, password)
            return SignUpResult(identity=self.identity_for(row), needs_verification=False)

    async def sign_in(self, email: str, password: str) -> Identity | MfaRequired:
        async with AsyncSessionFactory.public() as session:
            row = await LocalIdentityService(session).authenticate(email, password)
            identity = self.identity_for(row)
            membership = await TenantService(session).get_member_by_subject(identity.subject)
        if membership is None or membership.member.user_id is None:
            # First sign-in: SignInFlow provisions the family; nothing to ask yet.
            return identity
        if await self._mfa_enabled(membership):
            return MfaRequired(identity=identity, factor_id=LOCAL_FACTOR)
        return identity

    async def sign_out(self, identity: Identity) -> None:
        """Kaleta's own session is the only one."""

    async def delete_identity(self, subject: str) -> None:
        """Delete a member's login when their family is deleted.

        An instance administrator's login is kept: it is the instance's, not
        the family's, and deleting it could leave nobody to run the instance.
        Their next sign-in starts a new, empty family. Kept rather than refused
        so that deleting a family with several members never stops half-way.
        """
        identity_id = identity_id_of(subject)
        if identity_id is None:
            return
        async with AsyncSessionFactory.public() as session:
            identities = LocalIdentityService(session)
            row = await identities.get(identity_id)
            if row is None or row.is_instance_admin:
                return
            await identities.delete(identity_id)

    async def request_password_reset(self, email: str) -> None:
        raise ValidationError(_ADMIN_RESET)

    async def confirm_password_reset(self, token: str, new_password: str) -> None:
        raise ValidationError(_ADMIN_RESET)

    async def resend_confirmation(self, email: str) -> None:
        raise ValidationError(_NO_MAIL)

    async def request_magic_link(self, email: str) -> None:
        raise ValidationError(_NO_MAIL)

    async def verify_magic_link(self, token_hash: str) -> Identity | MfaRequired:
        raise ValidationError(_NO_MAIL)

    # ── Second factor ────────────────────────────────────────────────────────

    async def mfa_enrol(self, identity: Identity) -> FactorEnrolment:
        raise ValidationError(_LOCAL_MFA)

    async def mfa_challenge_verify(self, identity: Identity, factor_id: str, code: str) -> Identity:
        """Check the login code against the member's ``user_mfa`` row."""
        membership = await self._membership(identity)
        user_id = membership.member.user_id
        if user_id is None:
            raise ValidationError(_WRONG_CODE)
        with use_tenant(membership.context()):
            async with AsyncSessionFactory() as session:
                mfa = MfaService(session)
                if not await mfa.is_enabled(user_id):
                    raise ConflictError(_MFA_GONE)
                ok = await mfa.verify_code(user_id, code)
        if not ok:
            raise ValidationError(_WRONG_CODE)
        return identity

    async def mfa_unenrol(self, subject: str, factor_id: str) -> None:
        raise ValidationError(_LOCAL_MFA)

    async def consume_recovery_code(self, identity: Identity, code: str) -> bool:
        """A recovery code instead of the authenticator, at the login prompt."""
        membership = await self._membership(identity)
        user_id = membership.member.user_id
        if user_id is None:
            return False
        with use_tenant(membership.context()):
            async with AsyncSessionFactory() as session:
                mfa = MfaService(session)
                if not await mfa.is_enabled(user_id):
                    raise ConflictError(_MFA_GONE)
                return await mfa.consume_recovery_code(user_id, code)

    # ── Internals ────────────────────────────────────────────────────────────

    @staticmethod
    async def _membership(identity: Identity) -> TenantMembership:
        async with AsyncSessionFactory.public() as session:
            membership = await TenantService(session).get_member_by_subject(identity.subject)
        if membership is None:
            raise ValidationError(_WRONG_CODE)
        return membership

    @staticmethod
    async def _mfa_enabled(membership: TenantMembership) -> bool:
        user_id = membership.member.user_id
        if user_id is None:
            return False
        with use_tenant(membership.context()):
            async with AsyncSessionFactory() as session:
                return await MfaService(session).is_enabled(user_id)
