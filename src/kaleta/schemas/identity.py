# SPDX-License-Identifier: AGPL-3.0-or-later
"""Who signed in, as an ``AuthProvider`` reports it (``kaleta.auth.providers``).

Here rather than beside the providers so that services — ``TenantService``
provisions an account for an identity — can take one without importing the
auth layer above them.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["FactorEnrolment", "Identity", "MfaRequired", "RegistrationMode", "SignUpResult"]


class Identity(BaseModel):
    """A person the identity provider vouches for.

    ``subject`` is the provider's opaque, stable id: ``str(user.id)`` locally,
    the GoTrue user id with Supabase. ``email`` is the local username on a
    self-hosted install, which has no e-mail.
    """

    model_config = ConfigDict(frozen=True)

    subject: str
    email: str
    email_verified: bool
    #: The provider's access token for this sign-in, when it issued one. Never
    #: stored in the session and never printed.
    access_token: str | None = Field(default=None, repr=False, exclude=True)


class MfaRequired(BaseModel):
    """The password was right; a second factor has to follow before sign-in."""

    model_config = ConfigDict(frozen=True)

    identity: Identity
    factor_id: str


class FactorEnrolment(BaseModel):
    """A second factor the provider has minted but nobody has proved yet.

    ``secret`` and ``uri`` are what the authenticator app needs; they are shown
    once in the setup dialog and never stored by Kaleta.
    """

    model_config = ConfigDict(frozen=True)

    factor_id: str
    secret: str = Field(repr=False)
    uri: str = Field(repr=False)


class SignUpResult(BaseModel):
    """What sign-up produced: an identity to sign in now, or an e-mail to confirm."""

    model_config = ConfigDict(frozen=True)

    identity: Identity | None
    needs_verification: bool


class RegistrationMode(enum.StrEnum):
    """Who may create a family on this instance (ADR-38).

    ``closed``: only the instance administrator (or ``tenant_admin.py``).
    ``invite``: an invitation link is needed (``hosted-household-sharing``).
    ``open``: anyone who reaches the sign-up page.
    """

    CLOSED = "closed"
    INVITE = "invite"
    OPEN = "open"
