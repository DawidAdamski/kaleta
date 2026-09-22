# SPDX-License-Identifier: AGPL-3.0-or-later
"""Time-based one-time passwords as a second factor, plus recovery codes.

The shared secret lives in :class:`~kaleta.models.user_mfa.UserMfa` under
column encryption; the recovery codes are argon2 hashes, one per unused code,
so the list in the database is worth nothing on its own.

Two rules this module exists to keep:

* a secret is not a second factor until the user has proved the authenticator
  holds it — ``enabled_at`` is set by :meth:`MfaService.confirm_enrolment` and
  by nothing else;
* a code works once. TOTP codes are valid for a whole 30-second step, which is
  long enough to read one off a shoulder and type it into a second browser, so
  the accepted step number is remembered and never accepted again.
"""

from __future__ import annotations

import io
import json
import logging
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime

import pyotp
import qrcode
import qrcode.image.svg
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import ConflictError, NotFoundError, ValidationError
from kaleta.models.user import User
from kaleta.models.user_mfa import MFA_KIND_TOTP, UserMfa
from kaleta.services.auth_service import AuthService

log = logging.getLogger(__name__)

#: Seconds per TOTP step — the interval every authenticator app assumes.
TOTP_INTERVAL = 30
#: How many steps either side of now are accepted, for clocks that drift.
TOTP_DRIFT_STEPS = 1
#: The issuer an authenticator app shows above the code.
TOTP_ISSUER = "Kaleta"

RECOVERY_CODE_COUNT = 10
RECOVERY_CODE_LENGTH = 10
#: Crockford-flavoured base32: no I, L, O or U, so nothing in a printed code
#: can be read back as something else.
_RECOVERY_ALPHABET = "ABCDEFGHJKMNPQRSTVWXYZ0123456789"


@dataclass(frozen=True)
class MfaStatus:
    """What the Settings card and ``GET /api/v1/auth/mfa`` report."""

    enabled: bool
    enrolment_started: bool
    enabled_at: datetime | None
    recovery_codes_remaining: int


@dataclass(frozen=True)
class MfaEnrolment:
    """Everything the enrolment dialog needs; shown once, never stored."""

    secret: str
    uri: str
    qr_svg: str


def normalise_code(code: str) -> str:
    """Strip the spaces and dashes people type or paste, and upper-case it."""
    return "".join(ch for ch in code.strip().upper() if ch.isalnum())


class MfaService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._hasher = PasswordHasher()

    # ── reads ────────────────────────────────────────────────────────────

    async def _row(self, user_id: int) -> UserMfa | None:
        result = await self.session.execute(select(UserMfa).where(UserMfa.user_id == user_id))
        return result.scalar_one_or_none()

    async def is_enabled(self, user_id: int) -> bool:
        row = await self._row(user_id)
        return row is not None and row.is_enabled

    async def status(self, user_id: int) -> MfaStatus:
        row = await self._row(user_id)
        if row is None:
            return MfaStatus(
                enabled=False,
                enrolment_started=False,
                enabled_at=None,
                recovery_codes_remaining=0,
            )
        return MfaStatus(
            enabled=row.is_enabled,
            enrolment_started=not row.is_enabled,
            enabled_at=row.enabled_at,
            recovery_codes_remaining=len(self._hashes(row)),
        )

    # ── enrolment ────────────────────────────────────────────────────────

    async def begin_enrolment(self, user_id: int) -> MfaEnrolment:
        """Mint a secret and return it with its QR code. Nothing is enabled yet."""
        user = await self.session.get(User, user_id)
        if user is None:
            msg = "User not found"
            raise NotFoundError(msg)
        row = await self._row(user_id)
        if row is not None and row.is_enabled:
            msg = "Two-factor authentication is already enabled."
            raise ConflictError(msg)

        secret = pyotp.random_base32()
        if row is None:
            row = UserMfa(user_id=user_id, kind=MFA_KIND_TOTP, totp_secret=secret)
            self.session.add(row)
        else:
            # A restarted enrolment replaces the unconfirmed secret, so a QR
            # abandoned in a closed tab stops being usable.
            row.totp_secret = secret
            row.last_used_counter = None
            row.recovery_codes_hash = "[]"
        await self.session.commit()

        uri = pyotp.TOTP(secret, interval=TOTP_INTERVAL).provisioning_uri(
            name=user.username,
            issuer_name=TOTP_ISSUER,
        )
        return MfaEnrolment(secret=secret, uri=uri, qr_svg=_qr_svg(uri))

    async def confirm_enrolment(self, user_id: int, code: str) -> list[str]:
        """Enable MFA once a code proves the app holds the secret; return recovery codes."""
        row = await self._row(user_id)
        if row is None:
            msg = "Start the two-factor setup before confirming it."
            raise ValidationError(msg)
        if row.is_enabled:
            msg = "Two-factor authentication is already enabled."
            raise ConflictError(msg)
        counter = self._matching_counter(row, code)
        if counter is None:
            await self._record_failure(user_id, event="mfa_enrol_failure")
            msg = "That code is not right. Check the app and try the current code."
            raise ValidationError(msg)
        row.enabled_at = datetime.now(UTC)
        row.last_used_counter = counter
        codes = self._new_recovery_codes(row)
        await self.session.commit()
        return codes

    # ── verification ─────────────────────────────────────────────────────

    async def verify_code(self, user_id: int, code: str) -> bool:
        """True when ``code`` is the current TOTP code and has not been used."""
        row = await self._row(user_id)
        if row is None or not row.is_enabled:
            return False
        counter = self._matching_counter(row, code)
        if counter is None:
            await self._record_failure(user_id, event="mfa_failure")
            return False
        row.last_used_counter = counter
        await self.session.commit()
        return True

    async def consume_recovery_code(self, user_id: int, code: str) -> bool:
        """True when ``code`` was an unused recovery code; it is spent either way."""
        row = await self._row(user_id)
        if row is None or not row.is_enabled:
            return False
        if await self._spend_recovery_code(row, code):
            return True
        await self._record_failure(user_id, event="mfa_failure")
        return False

    async def _spend_recovery_code(self, row: UserMfa, code: str) -> bool:
        """Consume the code against ``row``, writing no audit event of its own.

        The caller decides what a failure is called: a wrong code at the login
        prompt and a wrong code in the "turn it off" dialog are different
        events, and the audit log should be able to tell them apart.
        """
        candidate = normalise_code(code)
        if not candidate:
            return False
        hashes = self._hashes(row)
        for index, stored in enumerate(hashes):
            if not self._verify_hash(stored, candidate):
                continue
            del hashes[index]
            row.recovery_codes_hash = json.dumps(hashes)
            await self.session.commit()
            return True
        return False

    # ── management ───────────────────────────────────────────────────────

    async def regenerate_recovery_codes(self, user_id: int) -> list[str]:
        """Replace the whole set. Any code written down earlier stops working."""
        row = await self._row(user_id)
        if row is None or not row.is_enabled:
            msg = "Enable two-factor authentication before asking for recovery codes."
            raise ValidationError(msg)
        codes = self._new_recovery_codes(row)
        await self.session.commit()
        return codes

    async def disable(self, user_id: int, *, password: str, code: str) -> None:
        """Turn MFA off. Needs the password and a fresh code (or a recovery code)."""
        row = await self._row(user_id)
        if row is None or not row.is_enabled:
            msg = "Two-factor authentication is not enabled."
            raise ValidationError(msg)
        user = await self.session.get(User, user_id)
        if user is None:
            msg = "User not found"
            raise NotFoundError(msg)
        if not AuthService(self.session).verify_password(password, user.password_hash):
            await self._record_failure(user_id, event="mfa_disable_failure")
            msg = "That password is not right."
            raise ValidationError(msg)
        if self._matching_counter(row, code) is None and not await self._spend_recovery_code(
            row, code
        ):
            await self._record_failure(user_id, event="mfa_disable_failure")
            msg = "That code is not right."
            raise ValidationError(msg)
        await self.session.delete(row)
        await self.session.commit()

    async def disable_all(self) -> int:
        """Drop every enrolment. The CLI escape hatch for a lost authenticator.

        Removing a second factor from a shell leaves a trace in the audit log
        for the same reason removing it from the UI does: it is the one state
        change here that nobody had to prove anything to make.
        """
        from kaleta.db.audit import record_auth_event

        result = await self.session.execute(select(UserMfa))
        rows = list(result.scalars().all())
        if not rows:
            return 0
        usernames: list[str | None] = []
        for row in rows:
            user = await self.session.get(User, row.user_id)
            usernames.append(user.username if user is not None else None)
            await self.session.delete(row)
        await self.session.commit()
        for username in usernames:
            await record_auth_event(
                self.session,
                event="mfa_disabled_cli",
                username=username,
                success=True,
            )
        return len(rows)

    # ── internals ────────────────────────────────────────────────────────

    def _matching_counter(self, row: UserMfa, code: str) -> int | None:
        """The TOTP step ``code`` belongs to, or ``None`` if it is no good.

        A step at or below ``last_used_counter`` is refused even when the code
        itself is right: that is the replay this method exists to stop.
        """
        candidate = normalise_code(code)
        if not candidate.isdigit():
            return None
        totp = pyotp.TOTP(row.totp_secret, interval=TOTP_INTERVAL)
        now = int(time.time())
        used = row.last_used_counter
        for offset in range(-TOTP_DRIFT_STEPS, TOTP_DRIFT_STEPS + 1):
            for_time = now + offset * TOTP_INTERVAL
            counter = for_time // TOTP_INTERVAL
            if used is not None and counter <= used:
                continue
            if secrets.compare_digest(totp.at(for_time), candidate):
                return int(counter)
        return None

    def _hashes(self, row: UserMfa) -> list[str]:
        try:
            stored = json.loads(row.recovery_codes_hash or "[]")
        except json.JSONDecodeError:
            log.warning("Recovery code list for user %s is not valid JSON", row.user_id)
            return []
        if not isinstance(stored, list):
            return []
        return [item for item in stored if isinstance(item, str)]

    def _new_recovery_codes(self, row: UserMfa) -> list[str]:
        codes = [
            "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(RECOVERY_CODE_LENGTH))
            for _ in range(RECOVERY_CODE_COUNT)
        ]
        row.recovery_codes_hash = json.dumps([self._hasher.hash(code) for code in codes])
        return codes

    def _verify_hash(self, stored: str, candidate: str) -> bool:
        try:
            self._hasher.verify(stored, candidate)
            return True
        except (VerifyMismatchError, InvalidHashError):
            return False

    async def _record_failure(self, user_id: int, *, event: str) -> None:
        from kaleta.db.audit import record_auth_event

        user = await self.session.get(User, user_id)
        await record_auth_event(
            self.session,
            event=event,
            username=user.username if user is not None else None,
            success=False,
        )


def _qr_svg(uri: str) -> str:
    """The provisioning URI as an inline SVG element (no XML declaration).

    An SVG rather than a PNG data URI: it is a fraction of the bytes, it stays
    sharp when the dialog is resized, and it needs no image encoder.
    """
    image = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage)
    buffer = io.BytesIO()
    image.save(buffer)
    markup = buffer.getvalue().decode("utf-8")
    start = markup.find("<svg")
    return markup[start:] if start >= 0 else markup
