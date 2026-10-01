# SPDX-License-Identifier: AGPL-3.0-or-later
"""The one interface every login path goes through (ADR-35).

``KALETA_AUTH_BACKEND`` picks the implementation: ``local`` checks argon2
hashes in the ``users`` table, ``supabase`` asks Supabase Auth. Views and API
routes only ever see this protocol, so neither knows which one is in play.

Failures are typed: wrong credentials raise ``UnauthorizedError`` (an
unconfirmed e-mail its subclass ``EmailNotVerifiedError``), a provider that
cannot be reached ``ExternalServiceError``, an operation the backend does not
offer ``ValidationError`` with a sentence saying what to do instead.
"""

from __future__ import annotations

from typing import Protocol

from kaleta.schemas.identity import Identity, MfaRequired, SignUpResult

__all__ = ["AuthProvider", "Identity", "MfaRequired", "SignUpResult"]


class AuthProvider(Protocol):
    #: ``"local"`` or ``"supabase"`` — for the login page's form, never for
    #: branching on security decisions.
    name: str

    async def sign_up(self, email: str, password: str) -> SignUpResult: ...

    async def sign_in(self, email: str, password: str) -> Identity | MfaRequired: ...

    async def sign_out(self, identity: Identity) -> None: ...

    async def request_password_reset(self, email: str) -> None: ...

    async def confirm_password_reset(self, token: str, new_password: str) -> None: ...

    async def delete_identity(self, subject: str) -> None: ...
