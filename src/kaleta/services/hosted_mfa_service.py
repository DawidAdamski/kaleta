# SPDX-License-Identifier: AGPL-3.0-or-later
"""Two-factor authentication on the hosted instance, where Supabase Auth holds the factor.

Phase A's :class:`~kaleta.services.mfa_service.MfaService` keeps a TOTP secret
in ``user_mfa`` and checks codes itself. With ``KALETA_AUTH_BACKEND=supabase``
the identity provider does that instead: enrolment, the code check and the
``aal2`` session claim are GoTrue's, reached through a :class:`FactorGateway`
(``SupabaseAuthProvider`` is one). What Kaleta keeps is what Supabase does not
offer — the recovery codes — in the same ``user_mfa`` row, of kind
``MFA_KIND_SUPABASE``, so the Settings card, its status line and the step-up
window read exactly as they do locally.

Kaleta holds no GoTrue session between requests (its own session is the
session of record, and the provider's is ended straight after sign-in), so
every act here that needs one signs in for it: the password is asked again,
and the token it buys lives no longer than the call that needed it.

A recovery code is the one way past the factor that GoTrue knows nothing of.
Spending one at the login prompt removes the factor with the service-role key
and leaves the row behind with no ``enabled_at`` — the marker
:meth:`MfaService.reenrolment_required` reads to send the next sign-in to set
a new factor up.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError

from kaleta.exceptions import (
    ConflictError,
    ExternalServiceError,
    UnauthorizedError,
    ValidationError,
)
from kaleta.models.user_mfa import MFA_KIND_SUPABASE, UserMfa
from kaleta.schemas.identity import FactorEnrolment, Identity, MfaRequired
from kaleta.services.auth_service import AuthService
from kaleta.services.mfa_service import (
    RECOVERY_CODE_COUNT,
    MfaEnrolment,
    MfaService,
    normalise_code,
    qr_svg,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)

_ALREADY_ON = "Two-factor authentication is already enabled."
_NOT_ON = "Two-factor authentication is not enabled."


class FactorGateway(Protocol):
    """The part of an ``AuthProvider`` this service needs (structurally)."""

    async def sign_in(self, email: str, password: str) -> Identity | MfaRequired: ...

    async def sign_out(self, identity: Identity) -> None: ...

    async def mfa_enrol(self, identity: Identity) -> FactorEnrolment: ...

    async def mfa_challenge_verify(
        self, identity: Identity, factor_id: str, code: str
    ) -> Identity: ...

    async def mfa_unenrol(self, subject: str, factor_id: str) -> None: ...


@dataclass(frozen=True)
class HostedEnrolment(MfaEnrolment):
    """An unconfirmed provider factor, plus the ``aal1`` sign-in that minted it.

    Held by the setup dialog in memory and nowhere else: the identity carries
    an access token, which is never written to the session store or the
    database.
    """

    factor_id: str = ""
    identity: Identity | None = field(default=None, repr=False)


class HostedMfaService(MfaService):
    def __init__(self, session: AsyncSession, gateway: FactorGateway) -> None:
        super().__init__(session)
        self._gateway = gateway

    # ── enrolment ────────────────────────────────────────────────────────

    async def begin_hosted_enrolment(
        self, user_id: int, *, email: str, password: str
    ) -> HostedEnrolment:
        """Sign in with ``password`` and ask the provider for a new factor.

        The password is asked because nothing else here can vouch for the
        person at the browser to the provider: Kaleta keeps no GoTrue session.
        A wrong one is a ``ValidationError``, counted by the dialog like a
        wrong code.
        """
        if await self.is_enabled(user_id):
            raise ConflictError(_ALREADY_ON)
        try:
            signed = await self._gateway.sign_in(email, password)
        except UnauthorizedError as exc:
            await self._record_failure(user_id, event="mfa_enrol_failure")
            msg = "That password is not right."
            raise ValidationError(msg) from exc
        if isinstance(signed, MfaRequired):
            # The provider already has a verified factor this account's row
            # does not know about. Enrolling a second would leave the first
            # guarding the login with no recovery codes behind it.
            await self._end(signed.identity)
            raise ConflictError(_ALREADY_ON)
        try:
            factor = await self._gateway.mfa_enrol(signed)
        except Exception:
            await self._end(signed)
            raise
        return HostedEnrolment(
            secret=factor.secret,
            uri=factor.uri,
            qr_svg=qr_svg(factor.uri),
            factor_id=factor.factor_id,
            identity=signed,
        )

    async def abandon_hosted_enrolment(self, enrolment: HostedEnrolment) -> None:
        """Remove a factor that was minted and never confirmed.

        Best effort: a factor left unverified at the provider guards nothing,
        so failing to remove it is logged rather than shown.
        """
        identity = self._identity_of(enrolment)
        try:
            await self._gateway.mfa_unenrol(identity.subject, enrolment.factor_id)
        except (ExternalServiceError, ValidationError) as exc:
            log.warning("Could not remove an abandoned factor: %s", type(exc).__name__)
        await self._end(identity)

    async def confirm_hosted_enrolment(
        self, user_id: int, enrolment: HostedEnrolment, code: str
    ) -> list[str]:
        """Have the provider check ``code``; on success turn the factor on and mint recovery codes.

        The provider's answer comes first because it is the one that cannot
        be taken back cheaply: once GoTrue has verified the factor it guards
        the login, so the row written here only follows it.
        """
        identity = self._identity_of(enrolment)
        try:
            lifted = await self._gateway.mfa_challenge_verify(
                identity, enrolment.factor_id, normalise_code(code)
            )
        except ValidationError as exc:
            await self._record_failure(user_id, event="mfa_enrol_failure")
            msg = "That code is not right. Check the app and try the current code."
            raise ValidationError(msg) from exc
        # The verified session is the enrolment's own, lifted to aal2: ending
        # it ends the one the password opened.
        await self._end(lifted)

        codes = [self._new_recovery_code() for _ in range(RECOVERY_CODE_COUNT)]
        hashed = json.dumps([self._hasher.hash(recovery) for recovery in codes])
        now = datetime.now(UTC)
        existing = (
            await self.session.execute(
                select(UserMfa.id, UserMfa.enabled_at).where(UserMfa.user_id == user_id)
            )
        ).one_or_none()
        if existing is None:
            self.session.add(
                UserMfa(
                    user_id=user_id,
                    kind=MFA_KIND_SUPABASE,
                    totp_secret=enrolment.factor_id,
                    enabled_at=now,
                    recovery_codes_hash=hashed,
                )
            )
            try:
                await self.session.flush()
                claimed = True
            except IntegrityError:
                await self.session.rollback()
                claimed = False
        else:
            # Over a row with no `enabled_at` only — the marker a spent
            # recovery code leaves. A row another tab turned on meanwhile is
            # not overwritten.
            result = await self.session.execute(
                update(UserMfa)
                .where(UserMfa.id == existing.id, UserMfa.enabled_at.is_(None))
                .values(
                    kind=MFA_KIND_SUPABASE,
                    totp_secret=enrolment.factor_id,
                    enabled_at=now,
                    last_used_counter=None,
                    recovery_codes_hash=hashed,
                )
            )
            claimed = self._claimed(result)
        if not claimed:
            # Two tabs confirmed at once. The provider now holds two verified
            # factors; the one this tab added goes, the other tab's stays.
            await self._unenrol_quietly(identity.subject, enrolment.factor_id)
            raise ConflictError(_ALREADY_ON)
        await self._record(user_id, event="mfa_enabled", success=True, commit=False)
        await AuthService(self.session).revoke_sessions(user_id, commit=False)
        await self.session.commit()
        return codes

    # ── verification ─────────────────────────────────────────────────────

    async def prove(self, user_id: int, *, email: str, password: str, code: str) -> bool:
        """The step-up check: the password and a current code, both judged by the provider.

        Unthrottled, like every ``verify_*`` in ``MfaService``: the dialog
        counts failures on ``mfa_rate_limiter``. Recovery codes are not taken
        here — on the hosted path spending one removes the factor, which is a
        login-prompt decision, not a side effect of revoking an API token.
        """
        if not await self.is_enabled(user_id):
            return False
        lifted = await self._sign_in_with_code(email, password, code)
        if lifted is None:
            await self._record_failure(user_id, event="mfa_step_up_failure")
            return False
        await self._end(lifted)
        await self._record(user_id, event="mfa_step_up", success=True)
        return True

    async def recover(self, user_id: int, code: str, *, subject: str, factor_id: str) -> bool:
        """Accept a recovery code at the login prompt by removing the provider's factor.

        GoTrue cannot be told "this person proved a recovery code", so the
        factor it holds is removed with the service-role key instead, and the
        row is left with no ``enabled_at`` and no codes: the next sign-in is
        sent to set a new one up. A code that matches nothing removes nothing.

        Order matters, both ways. The code is *checked* first, so nothing at
        the provider moves for a guess; the provider's factor goes next, so a
        GoTrue outage or a missing service-role key costs no code (the person
        can simply try again); and only then is the code spent — in the same
        transaction that clears the row, so there is no state in which the
        code is gone but the marker is not, or the reverse.
        """
        row = await self._row(user_id)
        if row is None or not row.is_enabled or self._find_recovery_code(row, code) is None:
            await self._record_failure(user_id, event="mfa_failure")
            return False
        spent_from = row.recovery_codes_hash
        await self._gateway.mfa_unenrol(subject, factor_id)
        # Conditional on the set the code was found in: a second tab spending
        # a code meanwhile changed it, and that tab's recovery is the one that
        # stands.
        result = await self.session.execute(
            update(UserMfa)
            .where(
                UserMfa.id == row.id,
                UserMfa.enabled_at.is_not(None),
                UserMfa.recovery_codes_hash == spent_from,
            )
            .values(enabled_at=None, last_used_counter=None, recovery_codes_hash="[]")
        )
        if not self._claimed(result):
            await self.session.rollback()
            msg = "That recovery code was used in another tab."
            raise ConflictError(msg)
        await self._record(user_id, event="mfa_recovered", success=True, commit=False)
        # Whoever holds the lost authenticator may be signed in elsewhere.
        await AuthService(self.session).revoke_sessions(user_id, commit=False)
        await self.session.commit()
        return True

    # ── management ───────────────────────────────────────────────────────

    async def disable_hosted(self, user_id: int, *, email: str, password: str, code: str) -> None:
        """Turn the factor off: the password and a current code, then remove it at the provider.

        One message for a wrong password and a wrong code, as locally. Unlike
        locally, the two do not cost the same time — GoTrue refuses a wrong
        password before any code is looked at, and that ordering is the
        provider's. What keeps the difference from being a password oracle is
        the dialog's limiter (five tries a quarter of an hour) and GoTrue's own
        rate limit on ``/token``.
        """
        wrong = "That password or code is not right."
        if not await self.is_enabled(user_id):
            raise ConflictError(_NOT_ON)
        try:
            signed = await self._gateway.sign_in(email, password)
        except UnauthorizedError as exc:
            await self._record_failure(user_id, event="mfa_disable_failure")
            raise ValidationError(wrong) from exc
        if isinstance(signed, MfaRequired):
            lifted = await self._verify_quietly(signed, code)
            if lifted is None:
                await self._record_failure(user_id, event="mfa_disable_failure")
                raise ValidationError(wrong)
            await self._end(lifted)
            await self._gateway.mfa_unenrol(lifted.subject, signed.factor_id)
        else:
            # The provider has no verified factor left (removed in its
            # dashboard, say). The password is proved; the row is all there
            # is to turn off.
            await self._end(signed)
        result = await self.session.execute(
            delete(UserMfa).where(UserMfa.user_id == user_id, UserMfa.enabled_at.is_not(None))
        )
        claimed = self._claimed(result)
        if claimed:
            await self._record(user_id, event="mfa_disabled", success=True, commit=False)
            await AuthService(self.session).revoke_sessions(user_id, commit=False)
        await self.session.commit()
        if not claimed:
            raise ConflictError(_NOT_ON)

    # ── internals ────────────────────────────────────────────────────────

    async def _sign_in_with_code(self, email: str, password: str, code: str) -> Identity | None:
        """The ``aal2`` identity a right password and code buy, or ``None``."""
        try:
            signed = await self._gateway.sign_in(email, password)
        except UnauthorizedError:
            return None
        if not isinstance(signed, MfaRequired):
            # A provider with no verified factor cannot vouch for a code.
            await self._end(signed)
            return None
        return await self._verify_quietly(signed, code)

    async def _verify_quietly(self, pending: MfaRequired, code: str) -> Identity | None:
        try:
            return await self._gateway.mfa_challenge_verify(
                pending.identity, pending.factor_id, normalise_code(code)
            )
        except ValidationError:
            await self._end(pending.identity)
            return None

    async def _end(self, identity: Identity) -> None:
        """End a GoTrue session this service opened. Failing to is logged, not raised.

        Kaleta's session never depended on it; a provider session that could
        not be ended runs out with its token's expiry.
        """
        try:
            await self._gateway.sign_out(identity)
        except ExternalServiceError as exc:
            log.warning("Could not end a provider session: %s", type(exc).__name__)

    async def _unenrol_quietly(self, subject: str, factor_id: str) -> None:
        try:
            await self._gateway.mfa_unenrol(subject, factor_id)
        except (ExternalServiceError, ValidationError) as exc:
            log.warning("Could not remove a duplicate factor: %s", type(exc).__name__)

    @staticmethod
    def _identity_of(enrolment: HostedEnrolment) -> Identity:
        if enrolment.identity is None:
            msg = "Start the two-factor setup before confirming it."
            raise ConflictError(msg)
        return enrolment.identity
