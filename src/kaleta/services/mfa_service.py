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
from datetime import UTC, datetime, timedelta

import pyotp
import qrcode
import qrcode.image.svg
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from sqlalchemy import delete, or_, select, update
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

#: How long a proved second factor counts as fresh for a sensitive action.
#: The policy lives here, not in the session helper, so that a service can
#: judge the freshness of the proof it is handed rather than trusting a bool.
STEP_UP_WINDOW_MINUTES = 10
#: How long a password-accepted session may sit in front of the code prompt.
MFA_CHALLENGE_TTL_MINUTES = 10

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
        """Whether this user has a confirmed second factor.

        Reads one column on purpose. Loading the row would decrypt the secret,
        and a secret that cannot be decrypted — the state a rotated
        ``KALETA_SECRET_KEY`` leaves behind — would turn this into an error on
        the password step of every login, including the login of the person
        trying to get in and fix it.
        """
        result = await self.session.execute(
            select(UserMfa.enabled_at).where(UserMfa.user_id == user_id)
        )
        return result.scalar_one_or_none() is not None

    async def status(self, user_id: int) -> MfaStatus:
        """The card's view of the factor. Reads no secret, for the same reason."""
        result = await self.session.execute(
            select(UserMfa.enabled_at, UserMfa.recovery_codes_hash).where(
                UserMfa.user_id == user_id
            )
        )
        found = result.one_or_none()
        if found is None:
            return MfaStatus(
                enabled=False,
                enrolment_started=False,
                enabled_at=None,
                recovery_codes_remaining=0,
            )
        enabled_at, recovery_codes_hash = found
        return MfaStatus(
            enabled=enabled_at is not None,
            enrolment_started=enabled_at is None,
            enabled_at=enabled_at,
            recovery_codes_remaining=len(self._parse_hashes(recovery_codes_hash, user_id)),
        )

    async def step_up_required(self, user_id: int, verified_at: datetime | None) -> bool:
        """Whether a sensitive action should ask for a code first.

        The one implementation of the question. A view calls it to decide
        whether to raise the dialog; the services that enforce it ask the same
        two things, so the prompt and the refusal cannot drift apart.
        """
        if not await self.is_enabled(user_id):
            return False
        return not self.step_up_is_fresh(verified_at)

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
        if counter is None or not await self._claim_counter(row, counter):
            await self._record_failure(user_id, event="mfa_failure")
            return False
        return True

    @staticmethod
    def step_up_is_fresh(verified_at: datetime | None) -> bool:
        """True when a second factor proved that recently counts for a sensitive action."""
        if verified_at is None:
            return False
        stamp = verified_at if verified_at.tzinfo else verified_at.replace(tzinfo=UTC)
        return datetime.now(UTC) - stamp <= timedelta(minutes=STEP_UP_WINDOW_MINUTES)

    async def verify_challenge(self, user_id: int, code: str) -> bool:
        """A current TOTP code or an unused recovery code — whichever is to hand.

        What the login page splits into two fields (the user picks) a step-up
        dialog asks for in one: someone down to recovery codes because their
        authenticator is gone still has to be able to revoke an API token.
        Either way the code is spent, and a failure is one audit row, not two.
        """
        row = await self._row(user_id)
        if row is None or not row.is_enabled:
            return False
        counter = self._matching_counter(row, code)
        if counter is not None and await self._claim_counter(row, counter):
            return True
        if counter is None and await self._spend_recovery_code(row, code):
            return True
        await self._record_failure(user_id, event="mfa_step_up_failure")
        return False

    async def consume_recovery_code(self, user_id: int, code: str) -> bool:
        """True when ``code`` was an unused recovery code, which then spends it.

        A code that matches nothing spends nothing — there is no such code to
        cross off.
        """
        row = await self._row(user_id)
        if row is None or not row.is_enabled:
            return False
        if await self._spend_recovery_code(row, code):
            return True
        await self._record_failure(user_id, event="mfa_failure")
        return False

    def _find_recovery_code(self, row: UserMfa, code: str) -> int | None:
        """Which unused recovery code ``code`` is, without crossing it off."""
        candidate = normalise_code(code)
        if not candidate:
            return None
        for index, stored in enumerate(self._hashes(row)):
            if self._verify_hash(stored, candidate):
                return index
        return None

    async def _claim_counter(self, row: UserMfa, counter: int) -> bool:
        """Take the TOTP step ``counter`` for this row, once, across everybody.

        Read the counter, compare it, write it back and two tabs holding the
        same code both pass — which is the replay the counter exists to stop.
        The database decides instead: the row only moves if it is still behind
        the step being claimed.
        """
        result = await self.session.execute(
            update(UserMfa)
            .where(
                UserMfa.id == row.id,
                or_(UserMfa.last_used_counter.is_(None), UserMfa.last_used_counter < counter),
            )
            .values(last_used_counter=counter)
        )
        await self.session.commit()
        if int(getattr(result, "rowcount", 0) or 0) != 1:
            return False
        await self.session.refresh(row)
        return True

    async def _remove_recovery_code(self, row: UserMfa, index: int) -> bool:
        """Cross one code off, once. False when somebody else got there first."""
        current = row.recovery_codes_hash
        hashes = self._parse_hashes(current, row.user_id)
        if index >= len(hashes):
            return False
        del hashes[index]
        result = await self.session.execute(
            update(UserMfa)
            .where(UserMfa.id == row.id, UserMfa.recovery_codes_hash == current)
            .values(recovery_codes_hash=json.dumps(hashes))
        )
        await self.session.commit()
        if int(getattr(result, "rowcount", 0) or 0) != 1:
            return False
        await self.session.refresh(row)
        return True

    async def _spend_recovery_code(self, row: UserMfa, code: str) -> bool:
        """Consume the code against ``row``, writing no audit event of its own.

        The caller decides what a failure is called: a wrong code at the login
        prompt and a wrong code in the "turn it off" dialog are different
        events, and the audit log should be able to tell them apart.
        """
        index = self._find_recovery_code(row, code)
        if index is None:
            return False
        return await self._remove_recovery_code(row, index)

    # ── management ───────────────────────────────────────────────────────

    async def regenerate_recovery_codes(
        self,
        user_id: int,
        *,
        mfa_verified_at: datetime | None = None,
    ) -> list[str]:
        """Replace the whole set. Any code written down earlier stops working.

        Reissuing is a second-factor act for the same reason minting an API
        token is: ten fresh codes are ten fresh ways past the factor. The
        caller says when the code was last proved and this method judges
        whether that is recent enough, so the window is not a view's to widen.
        """
        row = await self._row(user_id)
        if row is None or not row.is_enabled:
            msg = "Enable two-factor authentication before asking for recovery codes."
            raise ValidationError(msg)
        if not self.step_up_is_fresh(mfa_verified_at):
            msg = "Confirm with a two-factor code before reissuing recovery codes."
            raise ValidationError(msg)
        codes = self._new_recovery_codes(row)
        await self.session.commit()
        return codes

    async def disable(self, user_id: int, *, password: str, code: str) -> None:
        """Turn MFA off. Needs the password and a fresh code (or a recovery code).

        One message for both halves, deliberately. Telling the two apart would
        make this dialog a password oracle for anyone at an already-signed-in
        browser — and one that answers without going past the login page's
        rate limiter.
        """
        wrong = "That password or code is not right."
        row = await self._row(user_id)
        if row is None or not row.is_enabled:
            msg = "Two-factor authentication is not enabled."
            raise ConflictError(msg)
        user = await self.session.get(User, user_id)
        if user is None:
            msg = "User not found"
            raise NotFoundError(msg)

        # Both halves are weighed before either is judged, and nothing is
        # spent until both are right. Returning early on a wrong password
        # would answer in one argon2 verify where a right password answers in
        # up to eleven, and that difference is a password oracle no matter
        # what the message says.
        password_ok = AuthService(self.session).verify_password(password, user.password_hash)
        counter = self._matching_counter(row, code)
        # Looked for whatever the TOTP check said. Skipping the scan when the
        # code already matched would answer a right code faster than a wrong
        # one, which tells an attacker their TOTP guess landed without their
        # ever having to know the password.
        recovery_index = self._find_recovery_code(row, code)
        if not password_ok or (counter is None and recovery_index is None):
            await self._record_failure(user_id, event="mfa_disable_failure")
            raise ValidationError(wrong)

        if (
            counter is None
            and recovery_index is not None
            and not await self._remove_recovery_code(row, recovery_index)
        ):
            # Somebody else spent that code between the check and here.
            await self._record_failure(user_id, event="mfa_disable_failure")
            raise ValidationError(wrong)
        # No counter is claimed here: the row itself goes, so there is nothing
        # left for a replayed code to be replayed against.
        await self.session.delete(row)
        await self.session.commit()

    async def disable_all(self) -> int:
        """Drop every enrolment. The CLI escape hatch for a lost authenticator.

        Removing a second factor from a shell leaves a trace in the audit log
        for the same reason removing it from the UI does: it is the one state
        change here that nobody had to prove anything to make.
        """
        from kaleta.db.audit import record_auth_event

        # Columns, not rows, and a bulk delete rather than the ORM's: this is
        # the way back from a rotated KALETA_SECRET_KEY, so it has to work
        # when every secret in the table is unreadable. Loading the objects
        # would decrypt them and fail before deleting anything — leaving the
        # locked-out owner with the new password and the old enrolment.
        result = await self.session.execute(select(UserMfa.user_id))
        user_ids = list(result.scalars().all())
        if not user_ids:
            return 0
        usernames: list[str | None] = []
        for user_id in user_ids:
            user = await self.session.get(User, user_id)
            usernames.append(user.username if user is not None else None)
        await self.session.execute(delete(UserMfa))
        await self.session.commit()
        for username in usernames:
            await record_auth_event(
                self.session,
                event="mfa_disabled_cli",
                username=username,
                success=True,
            )
        return len(user_ids)

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
        return self._parse_hashes(row.recovery_codes_hash, row.user_id)

    def _parse_hashes(self, raw: str | None, user_id: int) -> list[str]:
        try:
            stored = json.loads(raw or "[]")
        except json.JSONDecodeError:
            log.warning("Recovery code list for user %s is not valid JSON", user_id)
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
