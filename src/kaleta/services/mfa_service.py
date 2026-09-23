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
from typing import TYPE_CHECKING, Any, cast

import pyotp
import qrcode
import qrcode.image.svg
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from sqlalchemy import delete, or_, select, update
from sqlalchemy.engine import Result
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import ConflictError, NotFoundError, ValidationError
from kaleta.models.user import User
from kaleta.models.user_mfa import MFA_KIND_TOTP, UserMfa
from kaleta.services.auth_service import AuthService

if TYPE_CHECKING:
    from sqlalchemy.engine import CursorResult

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
RECOVERY_CODE_COUNT = 10
RECOVERY_CODE_LENGTH = 10
#: Crockford-flavoured base32: no I, L, O or U, so nothing in a printed code
#: can be read back as something else.
_RECOVERY_ALPHABET = "ABCDEFGHJKMNPQRSTVWXYZ0123456789"


@dataclass(frozen=True)
class MfaStatus:
    """What the Settings card and ``GET /api/v1/auth/mfa`` report."""

    enabled: bool
    enabled_at: datetime | None
    recovery_codes_remaining: int


@dataclass(frozen=True)
class MfaEnrolment:
    """Everything the enrolment dialog needs; shown once, never stored."""

    secret: str
    uri: str
    qr_svg: str


def normalise_code(code: str) -> str:
    """Strip the spaces and dashes people type or paste, and upper-case it.

    ASCII only. ``str.isalnum()`` is True for Arabic-Indic digits and every
    other Unicode numeral, and ``secrets.compare_digest`` raises ``TypeError``
    on a non-ASCII ``str`` — so ``٣٣٣٣٣٣`` typed at the code prompt used to
    come back as a 500 rather than "that code is not right". Nothing Kaleta
    issues and nothing an authenticator app produces is outside ASCII, so
    dropping the rest costs a real user nothing.
    """
    return "".join(ch for ch in code.strip().upper() if ch.isascii() and ch.isalnum())


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
                enabled_at=None,
                recovery_codes_remaining=0,
            )
        enabled_at, recovery_codes_hash = found
        return MfaStatus(
            enabled=enabled_at is not None,
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
        """Mint a secret and return it with its QR code. Nothing is enabled yet.

        Reads two columns rather than the row, and overwrites in place. Setting
        up a *new* factor must not depend on being able to read the old one —
        an unconfirmed row abandoned in a closed tab before a
        ``KALETA_SECRET_KEY`` rotation would otherwise make this button fail
        for good, with no enabled factor anywhere to explain why.
        """
        user = await self.session.get(User, user_id)
        if user is None:
            msg = "User not found"
            raise NotFoundError(msg)
        existing = (
            await self.session.execute(
                select(UserMfa.id, UserMfa.enabled_at).where(UserMfa.user_id == user_id)
            )
        ).one_or_none()
        if existing is not None and existing.enabled_at is not None:
            msg = "Two-factor authentication is already enabled."
            raise ConflictError(msg)

        secret = pyotp.random_base32()
        if existing is None:
            self.session.add(UserMfa(user_id=user_id, kind=MFA_KIND_TOTP, totp_secret=secret))
            try:
                await self.session.flush()
            except IntegrityError as exc:
                # Two first-time enrolments at once. The unique index on
                # user_id decides; the loser gets the same answer the update
                # branch gives, rather than a driver error the view cannot read.
                await self.session.rollback()
                msg = "Two-factor authentication is already enabled."
                raise ConflictError(msg) from exc
        else:
            # A restarted enrolment replaces the unconfirmed secret, so a QR
            # abandoned in a closed tab stops being usable.
            result = await self.session.execute(
                update(UserMfa)
                # Still unconfirmed, checked here and not only above: a
                # confirmation landing between the two would otherwise leave
                # the row enabled, holding a secret nobody has and no recovery
                # codes — locked out of a factor that says it is on.
                .where(UserMfa.id == existing.id, UserMfa.enabled_at.is_(None))
                .values(totp_secret=secret, last_used_counter=None, recovery_codes_hash="[]")
            )
            if not self._claimed(result):
                msg = "Two-factor authentication is already enabled."
                raise ConflictError(msg)
        await self.session.commit()

        uri = pyotp.TOTP(secret, interval=TOTP_INTERVAL).provisioning_uri(
            name=user.username,
            issuer_name=TOTP_ISSUER,
        )
        return MfaEnrolment(secret=secret, uri=uri, qr_svg=_qr_svg(uri))

    async def abandon_enrolment(self, user_id: int) -> bool:
        """Drop an enrolment that was started and never confirmed.

        `begin_enrolment` commits the secret before the QR is shown — it has
        to, because the code the user is about to type is checked against a
        stored row. Closing the dialog therefore used to leave a live secret
        in the database with nothing in the UI able to clear it, invisible to
        `status()` and uncounted by `disable_all()`.

        Conditional on `enabled_at IS NULL`, like every other write here: a
        confirmation landing in the gap between the cancel and this call keeps
        the factor the user just turned on.
        """
        result = await self.session.execute(
            delete(UserMfa).where(UserMfa.user_id == user_id, UserMfa.enabled_at.is_(None))
        )
        dropped = self._claimed(result)
        await self.session.commit()
        return dropped

    async def confirm_enrolment(self, user_id: int, code: str) -> list[str]:
        """Enable MFA once a code proves the app holds the secret; return recovery codes."""
        row = await self._row(user_id)
        if row is None:
            # A `ConflictError`, not a `ValidationError`: there is nothing
            # wrong with what the user typed, the enrolment they were
            # confirming stopped existing underneath them — `--disable-mfa`
            # from a shell, or another tab. The caller counts wrong guesses
            # and must not count this, or a stale setup dialog would lock the
            # login prompt out of a failure nobody could have avoided.
            msg = "Start the two-factor setup before confirming it."
            raise ConflictError(msg)
        if row.is_enabled:
            msg = "Two-factor authentication is already enabled."
            raise ConflictError(msg)
        counter = self._matching_counter(row, code)
        if counter is None:
            await self._record_failure(user_id, event="mfa_enrol_failure")
            msg = "That code is not right. Check the app and try the current code."
            raise ValidationError(msg)
        codes = [self._new_recovery_code() for _ in range(RECOVERY_CODE_COUNT)]
        # `recovery`, not `code`: this method's `code` parameter is the TOTP
        # code, and the two are not the same secret.
        hashed = json.dumps([self._hasher.hash(recovery) for recovery in codes])
        # Claimed, not assigned: two tabs confirming the same pending
        # enrolment would both succeed, and the second would overwrite the ten
        # codes the first had already shown its user.
        result = await self.session.execute(
            update(UserMfa)
            .where(UserMfa.id == row.id, UserMfa.enabled_at.is_(None))
            .values(
                enabled_at=datetime.now(UTC),
                last_used_counter=counter,
                recovery_codes_hash=hashed,
            )
        )
        claimed = self._claimed(result)
        if claimed:
            await self._record(user_id, event="mfa_enabled", success=True, commit=False)
        await self.session.commit()
        if not claimed:
            msg = "Two-factor authentication is already enabled."
            raise ConflictError(msg)
        await self.session.refresh(row)
        return codes

    # ── verification ─────────────────────────────────────────────────────

    async def verify_code(self, user_id: int, code: str) -> bool:
        """True when ``code`` is the current TOTP code and has not been used.

        Unthrottled: six digits fall to a few hundred thousand tries, so every
        caller has to count failures itself. The UI does it with
        ``mfa_rate_limiter``; anything new must do the same.
        """
        row = await self._row(user_id)
        if row is None or not row.is_enabled:
            return False
        counter = self._matching_counter(row, code)
        if counter is None or not await self._claim_counter(row, counter):
            await self._record_failure(user_id, event="mfa_failure")
            return False
        # Without this the log cannot tell a finished sign-in from a password
        # that was right and a prompt that was walked away from: the password
        # step already wrote its own success either way.
        await self._record(user_id, event="mfa_verified", success=True)
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

        Unthrottled, like :meth:`verify_code`: the caller counts the failures.

        What the login page splits into two fields (the user picks) a step-up
        dialog asks for in one: someone down to recovery codes because their
        authenticator is gone still has to be able to revoke an API token.
        Either way the code is spent, and a failure is one audit row, not two.

        Both outcomes are recorded under ``mfa_step_up``, distinct from the
        login prompt's ``mfa_verified``: this is the answer that unlocks
        minting a bearer token outliving the session, so the log should say
        which prompt was satisfied and not merely that one was.
        """
        row = await self._row(user_id)
        if row is None or not row.is_enabled:
            return False
        counter = self._matching_counter(row, code)
        if counter is not None and await self._claim_counter(row, counter):
            await self._record(user_id, event="mfa_step_up", success=True)
            return True
        if counter is None and await self._spend_recovery_code(row, code):
            # Above all this one: a recovery code spent here is crossed off
            # for good, and this is the row that says where it went.
            await self._record(user_id, event="mfa_step_up", success=True)
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
            await self._record(user_id, event="mfa_verified", success=True)
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
        claimed = self._claimed(result)
        await self.session.commit()
        if not claimed:
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
        claimed = self._claimed(result)
        await self.session.commit()
        if not claimed:
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

        And it leaves a row. A step-up inside the ten-minute window answers
        without raising a dialog, so without this the whole act — the owner's
        existing codes invalidated, ten new ones handed to whoever asked —
        could be absent from the log entirely.
        """
        row = await self._row(user_id)
        if row is None or not row.is_enabled:
            msg = "Enable two-factor authentication before asking for recovery codes."
            raise ValidationError(msg)
        if not self.step_up_is_fresh(mfa_verified_at):
            msg = "Confirm with a two-factor code before reissuing recovery codes."
            raise ValidationError(msg)
        codes = [self._new_recovery_code() for _ in range(RECOVERY_CODE_COUNT)]
        result = await self.session.execute(
            update(UserMfa)
            # Claimed against the set that was read, like every other write
            # here: two tabs reissuing at once would otherwise each show their
            # user ten codes, and only the last writer's would work.
            .where(UserMfa.id == row.id, UserMfa.recovery_codes_hash == row.recovery_codes_hash)
            .values(
                recovery_codes_hash=json.dumps([self._hasher.hash(recovery) for recovery in codes])
            )
        )
        claimed = self._claimed(result)
        if claimed:
            await self._record(user_id, event="mfa_recovery_reissued", success=True, commit=False)
        await self.session.commit()
        if not claimed:
            msg = "Your recovery codes changed while this page was open. Try again."
            raise ConflictError(msg)
        await self.session.refresh(row)
        return codes

    async def disable(self, user_id: int, *, password: str, code: str) -> None:
        """Turn MFA off. Needs the password and a fresh code (or a recovery code).

        One message for both halves, deliberately. Telling the two apart would
        make this dialog a password oracle for anyone at an already-signed-in
        browser — and one that answers without going past the login page's
        rate limiter.

        Two consequences of that choice, both priced and both fine:

        * the success path pays for the recovery-code search even when the
          TOTP code already matched — up to ten argon2 verifies, so roughly a
          second on default parameters. Skipping it when the TOTP matched is
          exactly the timing difference the paragraph above exists to remove,
          and this is an action anyone performs once.
        * a recovery code is spent before the DELETE is attempted, so losing
          the race below crosses one off and still raises. Harmless: the
          factor is off either way, so the code it spent was guarding nothing.
          The other order would be worse — deleting before the credential is
          proved.
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
        # Looked for whatever the TOTP check said, so that the reply does not
        # time differently depending on the password — which is the oracle
        # that matters, because the password is the reusable secret.
        #
        # What this does not hide is how good the *code* was: a matching
        # recovery code answers after however many hashes it took to find it,
        # and a wrong one always costs all ten. That leak is priced: a
        # recovery code carries about fifty bits, the dialog is throttled to
        # five tries a quarter of an hour, and buying it off would mean ten
        # argon2 verifies on every attempt including the ones that succeed.
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
        # A conditional DELETE, like every other write in this module: two
        # tabs turning the factor off at once, or a `--disable-mfa` landing
        # between the read above and this line, would otherwise raise
        # `StaleDataError` out of the unit-of-work — an unhandled exception
        # where the dialog has a sentence ready for exactly this.
        result = await self.session.execute(
            delete(UserMfa).where(UserMfa.id == row.id, UserMfa.enabled_at.is_not(None))
        )
        claimed = self._claimed(result)
        if claimed:
            await self._record(user_id, event="mfa_disabled", success=True, commit=False)
        # Only what the session is actually holding: the point is to keep a
        # deleted row out of the identity map, and a row that was never in it
        # needs no help. `expunge` raises on anything else.
        if row in self.session:
            self.session.expunge(row)
        await self.session.commit()
        if not claimed:
            msg = "Two-factor authentication is not enabled."
            raise ConflictError(msg)

    async def disable_all(self) -> int:
        """Drop every enrolment; return how many were actually switched on.

        The CLI escape hatch for a lost authenticator.

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
        result = await self.session.execute(
            select(UserMfa.user_id, UserMfa.enabled_at.is_not(None))
        )
        rows = list(result.all())
        if not rows:
            return 0
        # Counted for the message, not for the delete: an enrolment abandoned
        # at the QR screen leaves an unconfirmed row behind, and telling an
        # owner who never finished setting one up that we "removed 1" would be
        # a lie told to the one person least able to check it. The row still
        # goes — it holds a live secret — it just is not counted as a factor
        # that was ever guarding anything.
        enabled = sum(1 for _user_id, is_enabled in rows if is_enabled)
        # Only the confirmed ones get a row, for the same reason only they
        # are counted: an enrolment abandoned at the QR screen was never a
        # factor, so there is nothing about it to say was disabled.
        usernames: list[str | None] = []
        for user_id, is_enabled in rows:
            if not is_enabled:
                continue
            user = await self.session.get(User, user_id)
            usernames.append(user.username if user is not None else None)
        await self.session.execute(delete(UserMfa))
        # The trace goes in the same transaction as the removal. Committing
        # the delete first and writing the rows after would let the one
        # removal nobody had to prove anything to make be the one that leaves
        # no trace.
        for username in usernames:
            await record_auth_event(
                self.session,
                event="mfa_disabled_cli",
                username=username,
                success=True,
                commit=False,
            )
        await self.session.commit()
        return enabled

    # ── internals ────────────────────────────────────────────────────────

    def _matching_counter(self, row: UserMfa, code: str) -> int | None:
        """The TOTP step ``code`` belongs to, or ``None`` if it is no good.

        A step at or below ``last_used_counter`` is refused even when the code
        itself is right: that is the replay this method exists to stop.
        """
        candidate = normalise_code(code)
        # `isascii()` as well as `isdigit()`: the normaliser already drops
        # non-ASCII, and this is the line that must not be the one relied on
        # if that ever changes — `compare_digest` below raises on such a str.
        if not (candidate.isascii() and candidate.isdigit()):
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

    def _new_recovery_code(self) -> str:
        return "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(RECOVERY_CODE_LENGTH))

    def _verify_hash(self, stored: str, candidate: str) -> bool:
        try:
            self._hasher.verify(stored, candidate)
            return True
        except (VerifyMismatchError, InvalidHashError):
            return False

    @staticmethod
    def _claimed(result: Result[Any]) -> bool:
        """Whether a conditional UPDATE matched the row it named.

        Always read before the commit. ``rowcount`` is memoized off a cursor
        that committing closes, and the ``or 0`` below would then read an
        unavailable count as "somebody else got there first" — a spurious
        conflict on a write that actually landed. The ``cast`` is only to
        escape ``execute()``'s declared ``Result`` return type — ``rowcount``
        lives on ``CursorResult``, which is what every DML statement here
        actually gets back. A ``getattr`` default would put the silent zero
        back in by another door, which is the harder one to spot.
        """
        return cast("CursorResult[Any]", result).rowcount == 1

    async def _record_failure(self, user_id: int, *, event: str) -> None:
        await self._record(user_id, event=event, success=False)

    async def _record(
        self, user_id: int, *, event: str, success: bool, commit: bool = True
    ) -> None:
        """Write one auth event for ``user_id``.

        ``user_mfa`` is in the audit listener's skip list — auditing it would
        copy the decrypted secret into `audit_log` — so every change to a
        factor has to say so here or go unrecorded. The ones that matter most
        are the successes: a thief at a signed-in browser with the password
        and one code can turn the factor off, and a log holding only the
        guesses they fumbled on the way is a log that missed the theft.

        ``commit=False`` for the rows that record a change to the factor
        itself, so the trace lands in the same transaction as the thing it
        describes — what `disable_all()` already does. A crash between two
        commits would otherwise leave a factor turned off with nothing saying
        who turned it off, which is the one outcome this method exists to
        prevent.
        """
        from kaleta.db.audit import record_auth_event

        user = await self.session.get(User, user_id)
        await record_auth_event(
            self.session,
            event=event,
            username=user.username if user is not None else None,
            success=success,
            commit=commit,
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
