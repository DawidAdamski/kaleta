# SPDX-License-Identifier: AGPL-3.0-or-later
"""``KALETA_AUTH_BACKEND=local`` — the self-hosted install, exactly as before.

A thin wrapper over ``AuthService``: the username stays the login name (it is
what ``Identity.email`` carries here), the subject is ``str(user.id)``. The
forgotten-password path stays the CLI (``kaleta --reset-password``), because a
self-hosted install has no mail server to send a link through.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from kaleta.exceptions import UnauthorizedError, ValidationError
from kaleta.schemas.identity import FactorEnrolment, Identity, MfaRequired, SignUpResult
from kaleta.services import AuthService, MfaService, with_session

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from kaleta.models.user import User

_CLI_RESET = "On a self-hosted install, reset the password with `kaleta --reset-password`."
_NO_MAIL = "A self-hosted install sends no e-mail; sign in with your username and password."
_LOCAL_MFA = "On a self-hosted install, two-factor authentication is set up in Settings → Security."


class LocalAuthProvider:
    name = "local"

    @staticmethod
    def identity_for(user: User) -> Identity:
        return Identity(subject=str(user.id), email=user.username, email_verified=True)

    async def sign_up(self, email: str, password: str) -> SignUpResult:
        """Create the one account of an empty database."""
        username = email.strip()

        async def _create(session: AsyncSession) -> Identity:
            auth = AuthService(session)
            if await auth.auth_state() != "no_user":
                msg = "An account already exists."
                raise ValidationError(msg)
            user = await auth.create_user(username, password)
            await auth.record_login(username=user.username, success=True)
            return self.identity_for(user)

        identity = await with_session(_create)
        return SignUpResult(identity=identity, needs_verification=False)

    async def sign_in(self, email: str, password: str) -> Identity | MfaRequired:
        username = email.strip()

        async def _try(session: AsyncSession) -> Identity | MfaRequired:
            auth = AuthService(session)
            # `authenticate` refuses a row without a local password hash.
            user = await auth.authenticate(username, password)
            if user is None:
                await auth.record_login(username=username or None, success=False)
                msg = "Invalid username or password."
                raise UnauthorizedError(msg)
            await auth.record_login(username=user.username, success=True)
            identity = self.identity_for(user)
            if await MfaService(session).is_enabled(user.id):
                return MfaRequired(identity=identity, factor_id=identity.subject)
            return identity

        return await with_session(_try)

    async def sign_out(self, identity: Identity) -> None:
        """Nothing to tell anyone: the session store is the only session."""

    async def request_password_reset(self, email: str) -> None:
        raise ValidationError(_CLI_RESET)

    async def confirm_password_reset(self, token: str, new_password: str) -> None:
        raise ValidationError(_CLI_RESET)

    async def delete_identity(self, subject: str) -> None:
        msg = "A self-hosted install deletes its account by deleting its database."
        raise ValidationError(msg)

    async def resend_confirmation(self, email: str) -> None:
        raise ValidationError(_NO_MAIL)

    async def request_magic_link(self, email: str) -> None:
        raise ValidationError(_NO_MAIL)

    async def verify_magic_link(self, token_hash: str) -> Identity | MfaRequired:
        raise ValidationError(_NO_MAIL)

    async def mfa_enrol(self, identity: Identity) -> FactorEnrolment:
        raise ValidationError(_LOCAL_MFA)

    async def mfa_challenge_verify(self, identity: Identity, factor_id: str, code: str) -> Identity:
        raise ValidationError(_LOCAL_MFA)

    async def mfa_unenrol(self, subject: str, factor_id: str) -> None:
        raise ValidationError(_LOCAL_MFA)
