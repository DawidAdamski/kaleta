# SPDX-License-Identifier: AGPL-3.0-or-later
"""``KALETA_AUTH_BACKEND=fake`` — the hosted flow on a laptop, without Supabase.

Debug only: the settings refuse it unless ``KALETA_DEBUG=true``. It stands in
for Supabase Auth in ``compose.hosted-dev.yml`` so sign-up, provisioning,
unlock and account deletion can be exercised with nothing but Postgres.

Every address is taken as confirmed the moment it signs up — there is no mail
to send — so sign-up signs straight in. Identities live in one JSON file
(argon2 hashes, never the password) beside the rest of the instance's state, so
a restarted container still knows them. There is no second factor, no
password reset and no magic link: those are GoTrue's, and the forms that would
call them get a sentence saying so.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from kaleta.exceptions import ConflictError, UnauthorizedError, ValidationError
from kaleta.schemas.identity import FactorEnrolment, Identity, MfaRequired, SignUpResult

logger = logging.getLogger(__name__)

_DEFAULT_STORE = Path.home() / ".kaleta" / "fake-auth.json"
_NO_MAIL = "The debug sign-in backend sends no e-mail; every address is confirmed at sign-up."
_NO_MFA = "The debug sign-in backend has no second factor."
#: The subject namespace: a stable id per address, like a GoTrue user id.
_SUBJECT_NAMESPACE = uuid.UUID("6f1d2c1e-6a4e-4d0b-9a59-6b3c1f0d9e21")


class FakeAuthProvider:
    name = "fake"
    email_login = True

    def __init__(self, store_path: Path | None = None) -> None:
        self._path = store_path or _DEFAULT_STORE
        self._hasher = PasswordHasher()
        self._lock = asyncio.Lock()

    # ── Store ────────────────────────────────────────────────────────────────

    def _load(self) -> dict[str, dict[str, str]]:
        if not self._path.is_file():
            return {}
        data = json.loads(self._path.read_text(encoding="utf-8"))
        return {str(k): dict(v) for k, v in data.items()}

    def _save(self, users: dict[str, dict[str, str]]) -> None:
        self._path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(users, indent=2, sort_keys=True), encoding="utf-8")
        os.chmod(tmp, 0o600)
        tmp.replace(self._path)

    @staticmethod
    def _normalise(email: str) -> str:
        return email.strip().lower()

    @staticmethod
    def _identity(email: str, subject: str) -> Identity:
        return Identity(subject=subject, email=email, email_verified=True)

    # ── AuthProvider ─────────────────────────────────────────────────────────

    async def sign_up(self, email: str, password: str) -> SignUpResult:
        address = self._normalise(email)
        if "@" not in address:
            msg = "Enter an e-mail address."
            raise ValidationError(msg)
        async with self._lock:
            users = self._load()
            if address in users:
                msg = "An account with this e-mail address already exists."
                raise ConflictError(msg)
            subject = str(uuid.uuid5(_SUBJECT_NAMESPACE, address))
            users[address] = {"subject": subject, "password_hash": self._hasher.hash(password)}
            self._save(users)
        logger.info("Fake auth: signed up %s", subject)
        return SignUpResult(identity=self._identity(address, subject), needs_verification=False)

    async def sign_in(self, email: str, password: str) -> Identity | MfaRequired:
        address = self._normalise(email)
        user = self._load().get(address)
        if user is None or not self._password_matches(user["password_hash"], password):
            msg = "Invalid e-mail or password."
            raise UnauthorizedError(msg)
        return self._identity(address, user["subject"])

    def _password_matches(self, password_hash: str, password: str) -> bool:
        try:
            return self._hasher.verify(password_hash, password)
        except (VerificationError, InvalidHashError):
            return False

    async def sign_out(self, identity: Identity) -> None:
        """No provider session outlives the sign-in, so nothing to end."""

    async def delete_identity(self, subject: str) -> None:
        async with self._lock:
            users = self._load()
            remaining = {k: v for k, v in users.items() if v["subject"] != subject}
            if len(remaining) != len(users):
                self._save(remaining)

    async def request_password_reset(self, email: str) -> None:
        raise ValidationError(_NO_MAIL)

    async def confirm_password_reset(self, token: str, new_password: str) -> None:
        raise ValidationError(_NO_MAIL)

    async def resend_confirmation(self, email: str) -> None:
        raise ValidationError(_NO_MAIL)

    async def request_magic_link(self, email: str) -> None:
        raise ValidationError(_NO_MAIL)

    async def verify_magic_link(self, token_hash: str) -> Identity | MfaRequired:
        raise ValidationError(_NO_MAIL)

    async def mfa_enrol(self, identity: Identity) -> FactorEnrolment:
        raise ValidationError(_NO_MFA)

    async def mfa_challenge_verify(self, identity: Identity, factor_id: str, code: str) -> Identity:
        raise ValidationError(_NO_MFA)

    async def mfa_unenrol(self, subject: str, factor_id: str) -> None:
        raise ValidationError(_NO_MFA)
