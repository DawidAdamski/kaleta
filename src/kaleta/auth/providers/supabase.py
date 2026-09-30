# SPDX-License-Identifier: AGPL-3.0-or-later
"""``KALETA_AUTH_BACKEND=supabase`` — Supabase Auth (GoTrue) over HTTPS.

Five GoTrue endpoints, called with ``httpx`` (already here through NiceGUI), so
no ``supabase-py``: ``/signup``, ``/token?grant_type=password``, ``/recover``,
``/verify`` + ``/user`` for the reset link, ``/logout``, and the admin
``/admin/users/{id}`` for deleting an identity with the service-role key.

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
from typing import Any

import httpx

from kaleta.exceptions import (
    EmailNotVerifiedError,
    ExternalServiceError,
    UnauthorizedError,
    ValidationError,
)
from kaleta.schemas.identity import Identity, MfaRequired, SignUpResult

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 10.0
#: GoTrue ``error_code`` values this provider treats specially.
_EMAIL_NOT_CONFIRMED = "email_not_confirmed"
_USER_ALREADY_EXISTS = "user_already_exists"
_WEAK_PASSWORD = "weak_password"  # noqa: S105 — an error code, not a password


class SupabaseAuthProvider:
    name = "supabase"

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
        identity = self._identity(self._json(response))
        if not identity.email_verified:
            msg = "Confirm your e-mail address before signing in."
            raise EmailNotVerifiedError(msg)
        return identity

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
