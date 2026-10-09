# SPDX-License-Identifier: AGPL-3.0-or-later
"""``KALETA_AUTH_BACKEND=supabase`` — Supabase Auth (GoTrue) over HTTPS.

A handful of GoTrue endpoints, called with ``httpx`` (already here through
NiceGUI), so no ``supabase-py``: ``/signup``, ``/token?grant_type=password``,
``/recover``, ``/verify`` + ``/user`` for the reset link, ``/resend`` for a
lost confirmation e-mail, ``/otp`` + ``/verify`` for magic-link sign-in,
``/logout``, and the admin ``/admin/users/{id}`` for deleting an identity with
the service-role key. The second factor is GoTrue's too: ``/factors`` enrols a
TOTP factor, ``/factors/{id}/challenge`` + ``/verify`` lift a session from
``aal1`` to ``aal2``, and the admin ``/admin/users/{id}/factors/{id}`` removes
one with the service-role key.

A password (or magic-link) sign-in of someone with a verified factor comes
back from GoTrue as an ``aal1`` session; this provider reports that as
``MfaRequired`` and keeps the ``aal1`` token on the identity, because it is
the token the code has to be checked with.

Every "send an e-mail" call answers the same whether or not the address has an
account, is already confirmed, or GoTrue's mail rate limit was hit: the forms
that call them must not tell anyone which addresses exist. Only a server error
is reported.

The access token GoTrue returns is checked against the user object it came
with — its ``sub`` and ``email`` claims must name the same person. The
signature is not verified here: the token arrives directly from GoTrue over
TLS in answer to our own request, so the channel is what vouches for it.
Kaleta's own session is the session of record; the GoTrue session is ended
straight after sign-in (``sign_out``) so no refresh token outlives the login.

Nothing from here is logged with a secret in it: not the password, not a
token, not the service-role key.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import secrets
from typing import Any
from urllib.parse import quote

import httpx

from kaleta.exceptions import (
    ConflictError,
    EmailNotVerifiedError,
    ExternalServiceError,
    UnauthorizedError,
    ValidationError,
)
from kaleta.schemas.identity import FactorEnrolment, Identity, MfaRequired, SignUpResult

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 10.0
#: GoTrue ``error_code`` values this provider treats specially.
_EMAIL_NOT_CONFIRMED = "email_not_confirmed"
_USER_ALREADY_EXISTS = "user_already_exists"
_WEAK_PASSWORD = "weak_password"  # noqa: S105 — an error code, not a password
#: The ``aal`` claim of a session that has proved its second factor.
_AAL2 = "aal2"
#: What the authenticator app shows above the code.
_TOTP_ISSUER = "Kaleta"


class SupabaseAuthProvider:
    name = "supabase"
    email_login = True

    def __init__(
        self,
        *,
        url: str,
        anon_key: str,
        service_role_key: str | None = None,
        public_url: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base = url.rstrip("/") + "/auth/v1"
        self._anon_key = anon_key
        self._service_role_key = service_role_key
        self._public_url = public_url.rstrip("/") if public_url else None
        self._transport = transport

    # ── Protocol ─────────────────────────────────────────────────────────────

    async def sign_up(self, email: str, password: str) -> SignUpResult:
        params = self._redirect("/login?reason=verified")
        response = await self._request(
            "POST", "/signup", json={"email": email.strip(), "password": password}, params=params
        )
        if response.status_code >= 400:
            code = self._error_code(response)
            if code == _USER_ALREADY_EXISTS:
                # Same answer as a fresh sign-up, so the form cannot be used to
                # find out which addresses have an account.
                return SignUpResult(identity=None, needs_verification=True)
            if code == _WEAK_PASSWORD or response.status_code == 422:
                raise ValidationError(self._error_message(response))
            raise self._unusable(response)
        body = self._json(response)
        # With e-mail confirmation on, GoTrue answers with the bare user; with
        # it off (a local dev stack), with a whole session.
        user = body.get("user") if isinstance(body.get("user"), dict) else body
        if "access_token" in body:
            return SignUpResult(identity=self._identity(body), needs_verification=False)
        confirmed = isinstance(user, dict) and bool(user.get("email_confirmed_at"))
        return SignUpResult(identity=None, needs_verification=not confirmed)

    async def sign_in(self, email: str, password: str) -> Identity | MfaRequired:
        response = await self._request(
            "POST",
            "/token",
            params={"grant_type": "password"},
            json={"email": email.strip(), "password": password},
        )
        if response.status_code in (400, 401, 422):
            if self._error_code(response) == _EMAIL_NOT_CONFIRMED:
                msg = "Confirm your e-mail address before signing in."
                raise EmailNotVerifiedError(msg)
            msg = "Invalid e-mail or password."
            raise UnauthorizedError(msg)
        if response.status_code >= 400:
            raise self._unusable(response)
        body = self._json(response)
        identity = self._identity(body)
        if not identity.email_verified:
            msg = "Confirm your e-mail address before signing in."
            raise EmailNotVerifiedError(msg)
        return self._second_factor(body, identity)

    async def sign_out(self, identity: Identity) -> None:
        if not identity.access_token:
            return
        response = await self._request(
            "POST",
            "/logout",
            params={"scope": "local"},
            bearer=identity.access_token,
        )
        # A token GoTrue no longer knows is already signed out.
        if response.status_code >= 400 and response.status_code not in (401, 403, 404):
            raise self._unusable(response)

    async def request_password_reset(self, email: str) -> None:
        response = await self._request(
            "POST",
            "/recover",
            json={"email": email.strip()},
            params=self._redirect("/reset-password"),
        )
        # Rate limits and unknown addresses alike end in the same "check your
        # inbox": the form must not tell anyone which addresses exist.
        if response.status_code >= 500:
            raise self._unusable(response)

    async def confirm_password_reset(self, token: str, new_password: str) -> None:
        verify = await self._request(
            "POST", "/verify", json={"type": "recovery", "token_hash": token}
        )
        if verify.status_code >= 400:
            msg = "This password reset link is invalid or has expired."
            raise ValidationError(msg)
        access_token = self._json(verify).get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise self._unusable(verify)
        update = await self._request(
            "PUT", "/user", json={"password": new_password}, bearer=access_token
        )
        if update.status_code == 422:
            raise ValidationError(self._error_message(update))
        if update.status_code >= 400:
            raise self._unusable(update)
        await self.sign_out(
            Identity(subject="", email="", email_verified=True, access_token=access_token)
        )

    async def resend_confirmation(self, email: str) -> None:
        response = await self._request(
            "POST",
            "/resend",
            json={"type": "signup", "email": email.strip()},
            params=self._redirect("/login?reason=verified"),
        )
        if response.status_code >= 500:
            raise self._unusable(response)

    async def request_magic_link(self, email: str) -> None:
        # `create_user: false`: a link signs in an existing account and never
        # makes one — sign-up stays e-mail + password (see the plan).
        response = await self._request(
            "POST",
            "/otp",
            json={"email": email.strip(), "create_user": False},
            params=self._redirect("/auth/magic"),
        )
        if response.status_code >= 500:
            raise self._unusable(response)

    async def verify_magic_link(self, token_hash: str) -> Identity | MfaRequired:
        response = await self._request(
            "POST", "/verify", json={"type": "magiclink", "token_hash": token_hash}
        )
        if response.status_code >= 500:
            raise self._unusable(response)
        if response.status_code >= 400:
            msg = "This sign-in link is invalid or has expired."
            raise ValidationError(msg)
        body = self._json(response)
        identity = self._identity(body)
        if not identity.email_verified:
            msg = "Confirm your e-mail address before signing in."
            raise EmailNotVerifiedError(msg)
        # A link proves the inbox, which is the first factor's job: someone
        # with a verified factor still owes the code.
        return self._second_factor(body, identity)

    async def delete_identity(self, subject: str) -> None:
        if not self._service_role_key:
            msg = "KALETA_SUPABASE_SERVICE_ROLE_KEY is required to delete an identity."
            raise ValidationError(msg)
        response = await self._request(
            "DELETE",
            f"/admin/users/{subject}",
            bearer=self._service_role_key,
            api_key=self._service_role_key,
        )
        if response.status_code >= 400 and response.status_code != 404:
            raise self._unusable(response)

    # ── Second factor ────────────────────────────────────────────────────────

    async def mfa_enrol(self, identity: Identity) -> FactorEnrolment:
        """Mint an unverified TOTP factor for the signed-in ``identity``.

        Nothing guards a login until :meth:`mfa_challenge_verify` has accepted
        a code for it; an enrolment given up on is removed with
        :meth:`mfa_unenrol`.
        """
        token = self._token(identity)
        # A name of its own per attempt: GoTrue refuses a second factor under a
        # name the user already has, and an abandoned one may still be there.
        name = f"{_TOTP_ISSUER} {secrets.token_hex(4)}"
        response = await self._request(
            "POST",
            "/factors",
            json={"factor_type": "totp", "friendly_name": name, "issuer": _TOTP_ISSUER},
            bearer=token,
        )
        self._raise_for_factor(response)
        body = self._json(response)
        factor_id = body.get("id")
        totp = body.get("totp")
        if not isinstance(factor_id, str) or not factor_id or not isinstance(totp, dict):
            msg = "The sign-in service sent an incomplete factor."
            raise ExternalServiceError(msg)
        secret = totp.get("secret")
        uri = totp.get("uri")
        if not isinstance(secret, str) or not secret or not isinstance(uri, str) or not uri:
            msg = "The sign-in service sent an incomplete factor."
            raise ExternalServiceError(msg)
        return FactorEnrolment(factor_id=factor_id, secret=secret, uri=uri)

    async def mfa_challenge_verify(self, identity: Identity, factor_id: str, code: str) -> Identity:
        """Check ``code`` against the factor; return the ``aal2`` identity it buys.

        The identity that comes back carries GoTrue's fresh access token, and
        its ``aal`` claim is checked here — a ``200`` that did not lift the
        session is not a proved second factor. A wrong or expired code is a
        ``ValidationError``; a factor that no longer exists a ``ConflictError``.
        """
        token = self._token(identity)
        path = f"/factors/{quote(factor_id, safe='')}"
        challenge = await self._request("POST", f"{path}/challenge", bearer=token)
        self._raise_for_factor(challenge)
        challenge_id = self._json(challenge).get("id")
        if not isinstance(challenge_id, str) or not challenge_id:
            msg = "The sign-in service sent an incomplete challenge."
            raise ExternalServiceError(msg)
        verify = await self._request(
            "POST",
            f"{path}/verify",
            json={"challenge_id": challenge_id, "code": code},
            bearer=token,
        )
        if verify.status_code in (400, 422):
            msg = "That code is not right."
            raise ValidationError(msg)
        self._raise_for_factor(verify)
        lifted = self._identity(self._json(verify))
        if lifted.subject != identity.subject:
            msg = "The sign-in service sent a token for someone else."
            raise ExternalServiceError(msg)
        if decode_jwt_claims(lifted.access_token or "").get("aal") != _AAL2:
            msg = "The sign-in service did not confirm the second factor."
            raise ExternalServiceError(msg)
        return lifted

    async def mfa_unenrol(self, subject: str, factor_id: str) -> None:
        """Remove a factor with the service-role key; one already gone is fine.

        The service-role key rather than the user's token because the caller
        that needs this most — a recovery code at the login prompt — is the
        one holding no ``aal2`` session to remove a verified factor with.
        """
        if not self._service_role_key:
            # Not the user's mistake, so not a ValidationError: the login
            # prompt reads that as a wrong code and counts it against them.
            msg = (
                "This instance cannot remove a second factor: "
                "KALETA_SUPABASE_SERVICE_ROLE_KEY is not set."
            )
            raise ExternalServiceError(msg)
        response = await self._request(
            "DELETE",
            f"/admin/users/{quote(subject, safe='')}/factors/{quote(factor_id, safe='')}",
            bearer=self._service_role_key,
            api_key=self._service_role_key,
        )
        if response.status_code >= 400 and response.status_code != 404:
            raise self._unusable(response)

    @staticmethod
    def _token(identity: Identity) -> str:
        if not identity.access_token:
            msg = "Your sign-in has timed out. Sign in again."
            raise UnauthorizedError(msg)
        return identity.access_token

    def _raise_for_factor(self, response: httpx.Response) -> None:
        """The failures every ``/factors`` call shares, as typed errors."""
        if response.status_code < 400:
            return
        if response.status_code in (401, 403):
            # The token aged out (GoTrue's default is an hour) or was signed out.
            msg = "Your sign-in has timed out. Sign in again."
            raise UnauthorizedError(msg)
        if response.status_code == 404:
            msg = "That second factor no longer exists."
            raise ConflictError(msg)
        if response.status_code in (400, 422):
            raise ValidationError(self._error_message(response))
        raise self._unusable(response)

    @staticmethod
    def _second_factor(session: dict[str, Any], identity: Identity) -> Identity | MfaRequired:
        """``MfaRequired`` when the user behind ``session`` has a verified factor.

        Read from the user object GoTrue answered with rather than from the
        token: an ``aal1`` token says what this session proved, not what the
        account demands. Only ``verified`` factors count — an enrolment
        abandoned at the QR code never guards a login.
        """
        user = session.get("user")
        factors = user.get("factors") if isinstance(user, dict) else None
        if not isinstance(factors, list):
            return identity
        for factor in factors:
            if (
                isinstance(factor, dict)
                and factor.get("status") == "verified"
                and factor.get("factor_type") == "totp"
                and isinstance(factor.get("id"), str)
                and factor["id"]
            ):
                return MfaRequired(identity=identity, factor_id=factor["id"])
        return identity

    # ── HTTP ─────────────────────────────────────────────────────────────────

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
        bearer: str | None = None,
        api_key: str | None = None,
    ) -> httpx.Response:
        headers = {"apikey": api_key or self._anon_key}
        if bearer is not None:
            headers["Authorization"] = f"Bearer {bearer}"
        try:
            async with httpx.AsyncClient(
                transport=self._transport, timeout=_TIMEOUT_SECONDS
            ) as client:
                return await client.request(
                    method, self._base + path, json=json, params=params, headers=headers
                )
        except httpx.HTTPError as exc:
            logger.warning("Supabase Auth %s %s failed: %s", method, path, type(exc).__name__)
            msg = "The sign-in service is unreachable. Try again in a moment."
            raise ExternalServiceError(msg) from exc

    def _redirect(self, path: str) -> dict[str, str] | None:
        return {"redirect_to": self._public_url + path} if self._public_url else None

    @staticmethod
    def _json(response: httpx.Response) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError as exc:
            msg = "The sign-in service sent an unreadable answer."
            raise ExternalServiceError(msg) from exc
        if not isinstance(body, dict):
            msg = "The sign-in service sent an unreadable answer."
            raise ExternalServiceError(msg)
        return body

    @staticmethod
    def _error_code(response: httpx.Response) -> str | None:
        try:
            body = response.json()
        except ValueError:
            return None
        if not isinstance(body, dict):
            return None
        code = body.get("error_code") or body.get("error")
        return str(code) if code is not None else None

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        try:
            body = response.json()
        except ValueError:
            body = {}
        if isinstance(body, dict):
            for key in ("msg", "message", "error_description"):
                value = body.get(key)
                if isinstance(value, str) and value:
                    return value
        return "The sign-in service refused the request."

    @staticmethod
    def _unusable(response: httpx.Response) -> ExternalServiceError:
        logger.warning(
            "Supabase Auth answered %s %s with HTTP %s",
            response.request.method,
            response.request.url.path,
            response.status_code,
        )
        return ExternalServiceError("The sign-in service is not answering properly.")

    # ── Tokens ───────────────────────────────────────────────────────────────

    def _identity(self, session: dict[str, Any]) -> Identity:
        """An ``Identity`` from a GoTrue session, after checking its token's claims."""
        user = session.get("user")
        access_token = session.get("access_token")
        if not isinstance(user, dict) or not isinstance(access_token, str):
            msg = "The sign-in service sent an incomplete session."
            raise ExternalServiceError(msg)
        subject = user.get("id")
        email = user.get("email")
        if not isinstance(subject, str) or not subject or not isinstance(email, str):
            msg = "The sign-in service sent an incomplete user."
            raise ExternalServiceError(msg)
        # Unverified decode, deliberately: this token came straight from GoTrue
        # over TLS in answer to our own request. A token that ever arrives from
        # a browser or client instead must have its signature checked (JWKS or
        # the project's JWT secret) before any claim in it is believed.
        claims = decode_jwt_claims(access_token)
        claim_email = claims.get("email")
        if claims.get("sub") != subject or not isinstance(claim_email, str):
            msg = "The sign-in service sent a token for someone else."
            raise ExternalServiceError(msg)
        if claim_email.strip().lower() != email.strip().lower():
            msg = "The sign-in service sent a token for someone else."
            raise ExternalServiceError(msg)
        return Identity(
            subject=subject,
            email=email.strip().lower(),
            email_verified=bool(user.get("email_confirmed_at") or user.get("confirmed_at")),
            access_token=access_token,
        )


def decode_jwt_claims(token: str) -> dict[str, Any]:
    """The payload of a JWT, unverified — see the module docstring for why."""
    parts = token.split(".")
    if len(parts) != 3:
        msg = "The sign-in service sent a malformed token."
        raise ExternalServiceError(msg)
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        claims = json.loads(base64.urlsafe_b64decode(payload))
    except (binascii.Error, ValueError) as exc:
        msg = "The sign-in service sent a malformed token."
        raise ExternalServiceError(msg) from exc
    if not isinstance(claims, dict):
        msg = "The sign-in service sent a malformed token."
        raise ExternalServiceError(msg)
    return claims
