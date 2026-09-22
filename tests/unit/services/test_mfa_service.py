# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for MfaService.

Covers: KAL-AUTH-013, KAL-AUTH-014, KAL-AUTH-015
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta

import pyotp
import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.db import types as types_mod
from kaleta.db.types import FORMAT_AES_GCM
from kaleta.exceptions import ConflictError, EncryptionError, ValidationError
from kaleta.models.audit_log import AuditLog
from kaleta.models.user_mfa import UserMfa
from kaleta.services.auth_service import AuthService
from kaleta.services.mfa_service import (
    RECOVERY_CODE_COUNT,
    RECOVERY_CODE_LENGTH,
    STEP_UP_WINDOW_MINUTES,
    TOTP_INTERVAL,
    MfaService,
    normalise_code,
)
from tests.conftest import make_session_factory

PASSWORD = "owner-password-1"


@pytest_asyncio.fixture
async def user(session: AsyncSession):
    return await AuthService(session).create_user("owner", PASSWORD)


@pytest.fixture
def mfa(session: AsyncSession) -> MfaService:
    return MfaService(session)


def code_for(secret: str, *, offset_steps: int = 0) -> str:
    """The code an authenticator app would show ``offset_steps`` steps from now."""
    totp = pyotp.TOTP(secret, interval=TOTP_INTERVAL)
    return str(totp.at(int(time.time()) + offset_steps * TOTP_INTERVAL))


async def enrol(mfa: MfaService, user_id: int) -> tuple[str, list[str]]:
    enrolment = await mfa.begin_enrolment(user_id)
    codes = await mfa.confirm_enrolment(user_id, code_for(enrolment.secret))
    return enrolment.secret, codes


class TestEnrolment:
    @pytest.mark.asyncio
    async def test_begin_returns_a_secret_a_uri_and_a_qr(self, mfa: MfaService, user) -> None:
        enrolment = await mfa.begin_enrolment(user.id)
        assert enrolment.secret
        assert enrolment.uri.startswith("otpauth://totp/")
        assert "issuer=Kaleta" in enrolment.uri
        assert enrolment.qr_svg.startswith("<svg")

    @pytest.mark.asyncio
    async def test_beginning_enrolment_does_not_enable_anything(
        self, mfa: MfaService, user
    ) -> None:
        await mfa.begin_enrolment(user.id)
        assert await mfa.is_enabled(user.id) is False
        status = await mfa.status(user.id)
        assert status.enabled is False
        assert status.enabled_at is None

    @pytest.mark.asyncio
    async def test_a_wrong_code_does_not_confirm(self, mfa: MfaService, user) -> None:
        await mfa.begin_enrolment(user.id)
        with pytest.raises(ValidationError):
            await mfa.confirm_enrolment(user.id, "000000")
        assert await mfa.is_enabled(user.id) is False

    @pytest.mark.asyncio
    async def test_confirming_enables_and_hands_over_recovery_codes(
        self, mfa: MfaService, user
    ) -> None:
        """Covers: KAL-AUTH-013"""
        _secret, codes = await enrol(mfa, user.id)
        assert len(codes) == RECOVERY_CODE_COUNT
        assert {len(code) for code in codes} == {RECOVERY_CODE_LENGTH}
        assert len(set(codes)) == RECOVERY_CODE_COUNT
        assert await mfa.is_enabled(user.id) is True
        status = await mfa.status(user.id)
        assert status.enabled_at is not None
        assert status.recovery_codes_remaining == RECOVERY_CODE_COUNT

    @pytest.mark.asyncio
    async def test_restarting_enrolment_replaces_the_unconfirmed_secret(
        self, mfa: MfaService, user
    ) -> None:
        first = await mfa.begin_enrolment(user.id)
        second = await mfa.begin_enrolment(user.id)
        assert second.secret != first.secret
        with pytest.raises(ValidationError):
            await mfa.confirm_enrolment(user.id, code_for(first.secret))

    @pytest.mark.asyncio
    async def test_cannot_enrol_twice(self, mfa: MfaService, user) -> None:
        await enrol(mfa, user.id)
        with pytest.raises(ConflictError):
            await mfa.begin_enrolment(user.id)

    @pytest.mark.asyncio
    async def test_the_secret_is_not_stored_in_the_clear(
        self, mfa: MfaService, session: AsyncSession, user
    ) -> None:
        secret, _codes = await enrol(mfa, user.id)
        # Raw SQL on purpose: reading through the ORM would hand back the
        # decrypted string and prove nothing about what is on disk.
        raw = await session.execute(text("SELECT totp_secret FROM user_mfa"))
        stored = bytes(raw.scalar_one())
        assert secret.encode() not in stored
        assert stored[0] == FORMAT_AES_GCM


class TestVerification:
    @pytest.mark.asyncio
    async def test_the_current_code_is_accepted(self, mfa: MfaService, user) -> None:
        """Covers: KAL-AUTH-014"""
        secret, _codes = await enrol(mfa, user.id)
        # Enrolment consumed this step, so verify against the next one.
        assert await mfa.verify_code(user.id, code_for(secret, offset_steps=1)) is True

    @pytest.mark.asyncio
    async def test_a_code_one_step_behind_is_accepted_for_clock_drift(
        self, mfa: MfaService, user
    ) -> None:
        enrolment = await mfa.begin_enrolment(user.id)
        # Confirm with a code from two steps ahead so the drift window below
        # still lands above the consumed counter.
        await mfa.confirm_enrolment(user.id, code_for(enrolment.secret, offset_steps=-1))
        assert await mfa.verify_code(user.id, code_for(enrolment.secret)) is True

    @pytest.mark.asyncio
    async def test_a_code_far_outside_the_window_is_rejected(self, mfa: MfaService, user) -> None:
        secret, _codes = await enrol(mfa, user.id)
        assert await mfa.verify_code(user.id, code_for(secret, offset_steps=10)) is False

    @pytest.mark.asyncio
    async def test_the_same_code_cannot_be_used_twice(self, mfa: MfaService, user) -> None:
        """Covers: KAL-AUTH-014"""
        secret, _codes = await enrol(mfa, user.id)
        code = code_for(secret, offset_steps=1)
        assert await mfa.verify_code(user.id, code) is True
        assert await mfa.verify_code(user.id, code) is False

    @pytest.mark.asyncio
    async def test_nonsense_is_rejected_without_touching_the_counter(
        self, mfa: MfaService, session: AsyncSession, user
    ) -> None:
        secret, _codes = await enrol(mfa, user.id)
        assert await mfa.verify_code(user.id, "not-a-code") is False
        assert await mfa.verify_code(user.id, code_for(secret, offset_steps=1)) is True

    @pytest.mark.asyncio
    async def test_an_unconfirmed_enrolment_never_verifies(self, mfa: MfaService, user) -> None:
        enrolment = await mfa.begin_enrolment(user.id)
        assert await mfa.verify_code(user.id, code_for(enrolment.secret)) is False

    @pytest.mark.asyncio
    async def test_a_user_without_mfa_never_verifies(self, mfa: MfaService, user) -> None:
        assert await mfa.verify_code(user.id, "123456") is False


class TestStepUpChallenge:
    """`verify_challenge` takes either kind of code, in one prompt."""

    @pytest.mark.asyncio
    async def test_a_totp_code_is_accepted(self, mfa: MfaService, user) -> None:
        secret, _codes = await enrol(mfa, user.id)
        assert await mfa.verify_challenge(user.id, code_for(secret, offset_steps=1)) is True

    @pytest.mark.asyncio
    async def test_a_totp_code_is_still_single_use(self, mfa: MfaService, user) -> None:
        secret, _codes = await enrol(mfa, user.id)
        code = code_for(secret, offset_steps=1)
        assert await mfa.verify_challenge(user.id, code) is True
        assert await mfa.verify_challenge(user.id, code) is False

    @pytest.mark.asyncio
    async def test_a_recovery_code_is_accepted_and_spent(self, mfa: MfaService, user) -> None:
        _secret, codes = await enrol(mfa, user.id)
        assert await mfa.verify_challenge(user.id, codes[0]) is True
        assert await mfa.verify_challenge(user.id, codes[0]) is False
        status = await mfa.status(user.id)
        assert status.recovery_codes_remaining == RECOVERY_CODE_COUNT - 1

    @pytest.mark.asyncio
    async def test_a_wrong_code_is_one_audit_row_not_two(
        self, mfa: MfaService, session: AsyncSession, user
    ) -> None:
        """It is checked against both kinds, but it was one wrong answer."""
        await enrol(mfa, user.id)
        assert await mfa.verify_challenge(user.id, "000000") is False
        rows = (
            (await session.execute(select(AuditLog).where(AuditLog.operation == "AUTH")))
            .scalars()
            .all()
        )
        events = [json.loads(row.new_data or "{}")["event"] for row in rows]
        assert events.count("mfa_step_up_failure") == 1
        assert "mfa_failure" not in events

    @pytest.mark.asyncio
    async def test_a_user_without_mfa_never_passes(self, mfa: MfaService, user) -> None:
        assert await mfa.verify_challenge(user.id, "123456") is False


class TestTheAuditTrail:
    """Every refused code leaves a row saying which prompt refused it, and
    every change to the factor itself leaves one too — the ORM audit listener
    skips ``user_mfa``, so this service is the only thing that can."""

    async def _auth_events(self, session: AsyncSession) -> list[dict[str, object]]:
        rows = (
            (await session.execute(select(AuditLog).where(AuditLog.operation == "AUTH")))
            .scalars()
            .all()
        )
        return [json.loads(row.new_data or "{}") for row in rows]

    @pytest.mark.asyncio
    async def test_a_wrong_code_at_the_login_prompt(
        self, mfa: MfaService, session: AsyncSession, user
    ) -> None:
        await enrol(mfa, user.id)
        assert await mfa.verify_code(user.id, "000000") is False
        events = await self._auth_events(session)
        assert {"event": "mfa_failure", "username": "owner", "success": False} in events

    @pytest.mark.asyncio
    async def test_a_wrong_recovery_code_at_the_login_prompt(
        self, mfa: MfaService, session: AsyncSession, user
    ) -> None:
        await enrol(mfa, user.id)
        assert await mfa.consume_recovery_code(user.id, "ZZZZZZZZZZ") is False
        events = await self._auth_events(session)
        assert [e["event"] for e in events].count("mfa_failure") == 1

    @pytest.mark.asyncio
    async def test_a_wrong_code_during_enrolment(
        self, mfa: MfaService, session: AsyncSession, user
    ) -> None:
        await mfa.begin_enrolment(user.id)
        with pytest.raises(ValidationError):
            await mfa.confirm_enrolment(user.id, "000000")
        assert "mfa_enrol_failure" in [e["event"] for e in await self._auth_events(session)]

    @pytest.mark.asyncio
    async def test_a_wrong_answer_in_the_turn_off_dialog(
        self, mfa: MfaService, session: AsyncSession, user
    ) -> None:
        await enrol(mfa, user.id)
        with pytest.raises(ValidationError):
            await mfa.disable(user.id, password="wrong-password", code="000000")
        assert "mfa_disable_failure" in [e["event"] for e in await self._auth_events(session)]

    @pytest.mark.asyncio
    async def test_a_right_code_leaves_no_failure_behind(
        self, mfa: MfaService, session: AsyncSession, user
    ) -> None:
        secret, _codes = await enrol(mfa, user.id)
        assert await mfa.verify_code(user.id, code_for(secret, offset_steps=1)) is True
        events = await self._auth_events(session)
        assert [e for e in events if not e["success"]] == []
        assert {"event": "mfa_verified", "username": "owner", "success": True} in events

    @pytest.mark.asyncio
    async def test_the_whole_life_of_a_factor_is_on_the_record(
        self, mfa: MfaService, session: AsyncSession, user
    ) -> None:
        """``user_mfa`` is skipped by the ORM audit listener, so if the service
        does not write these rows nothing else will, and turning the factor off
        — the step a thief at a signed-in browser needs — leaves no trace."""
        # One code per step, and the drift window is one step wide: the
        # recovery code is what gets a second sign-in out of this test without
        # sleeping thirty seconds for a counter the enrolment has not spent.
        secret, codes = await enrol(mfa, user.id)
        assert await mfa.consume_recovery_code(user.id, codes[0]) is True
        await mfa.disable(user.id, password=PASSWORD, code=code_for(secret, offset_steps=1))

        events = [e for e in await self._auth_events(session) if e["success"]]
        assert [e["event"] for e in events] == [
            "mfa_enabled",
            "mfa_verified",
            "mfa_disabled",
        ]
        assert {e["username"] for e in events} == {user.username}


class TestRecoveryCodes:
    @pytest.mark.asyncio
    async def test_a_recovery_code_works_once(self, mfa: MfaService, user) -> None:
        """Covers: KAL-AUTH-015"""
        _secret, codes = await enrol(mfa, user.id)
        assert await mfa.consume_recovery_code(user.id, codes[0]) is True
        assert await mfa.consume_recovery_code(user.id, codes[0]) is False
        status = await mfa.status(user.id)
        assert status.recovery_codes_remaining == RECOVERY_CODE_COUNT - 1

    @pytest.mark.asyncio
    async def test_spacing_and_case_do_not_matter(self, mfa: MfaService, user) -> None:
        _secret, codes = await enrol(mfa, user.id)
        typed = f" {codes[0][:5].lower()}-{codes[0][5:].lower()} "
        assert await mfa.consume_recovery_code(user.id, typed) is True

    @pytest.mark.asyncio
    async def test_the_stored_list_holds_hashes_not_codes(
        self, mfa: MfaService, session: AsyncSession, user
    ) -> None:
        _secret, codes = await enrol(mfa, user.id)
        row = (await session.execute(select(UserMfa))).scalar_one()
        stored = json.loads(row.recovery_codes_hash)
        assert len(stored) == RECOVERY_CODE_COUNT
        assert all(item.startswith("$argon2") for item in stored)
        assert not any(code in row.recovery_codes_hash for code in codes)

    @pytest.mark.asyncio
    async def test_regenerating_invalidates_the_old_set(self, mfa: MfaService, user) -> None:
        _secret, codes = await enrol(mfa, user.id)
        fresh = await mfa.regenerate_recovery_codes(user.id, mfa_verified_at=datetime.now(UTC))
        assert set(fresh).isdisjoint(codes)
        assert await mfa.consume_recovery_code(user.id, codes[0]) is False
        assert await mfa.consume_recovery_code(user.id, fresh[0]) is True

    @pytest.mark.asyncio
    async def test_recovery_codes_need_mfa_to_be_on(self, mfa: MfaService, user) -> None:
        with pytest.raises(ValidationError):
            await mfa.regenerate_recovery_codes(user.id, mfa_verified_at=datetime.now(UTC))

    @pytest.mark.asyncio
    async def test_reissuing_needs_a_fresh_code(self, mfa: MfaService, user) -> None:
        """Ten fresh codes are ten fresh ways past the factor."""
        _secret, codes = await enrol(mfa, user.id)
        with pytest.raises(ValidationError):
            await mfa.regenerate_recovery_codes(user.id)
        stale = datetime.now(UTC) - timedelta(minutes=STEP_UP_WINDOW_MINUTES + 1)
        with pytest.raises(ValidationError):
            await mfa.regenerate_recovery_codes(user.id, mfa_verified_at=stale)
        # Nothing was reissued, so the codes handed out at enrolment still work.
        assert await mfa.consume_recovery_code(user.id, codes[0]) is True


class TestDisable:
    @pytest.mark.asyncio
    async def test_a_wrong_password_spends_nothing(self, mfa: MfaService, user) -> None:
        """Both halves are weighed, but a failed attempt must not cost a code.

        The check runs the recovery-code comparison whatever the password was
        — that is what stops the timing from betraying the password — so the
        code it matched has to survive the refusal.
        """
        _secret, codes = await enrol(mfa, user.id)
        with pytest.raises(ValidationError):
            await mfa.disable(user.id, password="wrong-password", code=codes[0])
        status = await mfa.status(user.id)
        assert status.recovery_codes_remaining == RECOVERY_CODE_COUNT
        assert await mfa.consume_recovery_code(user.id, codes[0]) is True

    @pytest.mark.asyncio
    async def test_the_same_sentence_for_either_half(self, mfa: MfaService, user) -> None:
        """Telling them apart would make this dialog a password oracle."""
        secret, _codes = await enrol(mfa, user.id)
        with pytest.raises(ValidationError) as wrong_password:
            await mfa.disable(
                user.id,
                password="wrong-password",
                code=code_for(secret, offset_steps=1),
            )
        with pytest.raises(ValidationError) as wrong_code:
            await mfa.disable(user.id, password=PASSWORD, code="000000")
        assert wrong_password.value.message == wrong_code.value.message

    @pytest.mark.asyncio
    async def test_disabling_what_is_not_on_is_a_conflict_not_a_bad_credential(
        self, mfa: MfaService, user
    ) -> None:
        """A stale dialog is not a wrong guess, and must not count as one."""
        with pytest.raises(ConflictError):
            await mfa.disable(user.id, password=PASSWORD, code="000000")

    @pytest.mark.asyncio
    async def test_disable_needs_the_password(self, mfa: MfaService, user) -> None:
        secret, _codes = await enrol(mfa, user.id)
        with pytest.raises(ValidationError):
            await mfa.disable(
                user.id,
                password="wrong-password",
                code=code_for(secret, offset_steps=1),
            )
        assert await mfa.is_enabled(user.id) is True

    @pytest.mark.asyncio
    async def test_disable_needs_a_code(self, mfa: MfaService, user) -> None:
        await enrol(mfa, user.id)
        with pytest.raises(ValidationError):
            await mfa.disable(user.id, password=PASSWORD, code="000000")
        assert await mfa.is_enabled(user.id) is True

    @pytest.mark.asyncio
    async def test_password_and_code_turn_it_off(self, mfa: MfaService, user) -> None:
        secret, _codes = await enrol(mfa, user.id)
        await mfa.disable(user.id, password=PASSWORD, code=code_for(secret, offset_steps=1))
        assert await mfa.is_enabled(user.id) is False

    @pytest.mark.asyncio
    async def test_a_recovery_code_also_turns_it_off(self, mfa: MfaService, user) -> None:
        _secret, codes = await enrol(mfa, user.id)
        await mfa.disable(user.id, password=PASSWORD, code=codes[3])
        assert await mfa.is_enabled(user.id) is False

    @pytest.mark.asyncio
    async def test_disable_all_clears_every_enrolment(self, mfa: MfaService, user) -> None:
        await enrol(mfa, user.id)
        assert await mfa.disable_all() == 1
        assert await mfa.is_enabled(user.id) is False

    @pytest.mark.asyncio
    async def test_disable_all_leaves_a_trace(
        self, mfa: MfaService, session: AsyncSession, user
    ) -> None:
        """It is the one removal nobody had to prove anything to make."""
        await enrol(mfa, user.id)
        await mfa.disable_all()
        rows = (
            (await session.execute(select(AuditLog).where(AuditLog.operation == "AUTH")))
            .scalars()
            .all()
        )
        events = [json.loads(row.new_data or "{}") for row in rows]
        assert {"event": "mfa_disabled_cli", "username": "owner", "success": True} in events

    @pytest.mark.asyncio
    async def test_disable_all_on_an_empty_table_is_quiet(
        self, mfa: MfaService, session: AsyncSession
    ) -> None:
        assert await mfa.disable_all() == 0
        rows = (await session.execute(select(AuditLog))).scalars().all()
        assert rows == []


@pytest_asyncio.fixture
async def abandoned_enrolment(mfa: MfaService, session: AsyncSession, user) -> int:
    """An unconfirmed enrolment, written while the key still worked."""
    user_id = int(user.id)
    await mfa.begin_enrolment(user_id)
    session.expunge_all()
    return user_id


@pytest_asyncio.fixture
async def enrolled_user_id(mfa: MfaService, session: AsyncSession, user) -> int:
    """A confirmed enrolment, written while the key still worked.

    The id is taken before anything is detached: once the identity map is
    cleared, reading it back would be IO in a place that cannot do IO.
    """
    user_id = int(user.id)
    await enrol(mfa, user_id)
    session.expunge_all()
    return user_id


class TestAfterAKeyRotation:
    """What still has to work when no secret in the table can be decrypted.

    `SECURITY.md` points a locked-out self-hoster at
    `kaleta --reset-password --disable-mfa`. If any of this decrypted the
    secret to do its job, that door would be shut too.
    """

    @pytest.fixture
    def rotated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(types_mod, "_key_source", lambda: b"a-different-key-" + b"x" * 16)

    @pytest.mark.asyncio
    async def test_reading_the_secret_really_does_fail(
        self, mfa: MfaService, enrolled_user_id: int, rotated: None
    ) -> None:
        with pytest.raises(EncryptionError):
            await mfa.verify_code(enrolled_user_id, "000000")

    @pytest.mark.asyncio
    async def test_an_abandoned_enrolment_does_not_block_a_new_one(
        self, mfa: MfaService, abandoned_enrolment: int, rotated: None
    ) -> None:
        """A QR left in a closed tab must not become a permanent blockage.

        There is no enabled factor in this case, so nothing points the owner
        at the CLI — the Set up button simply has to keep working.
        """
        enrolment = await mfa.begin_enrolment(abandoned_enrolment)
        assert enrolment.secret

    @pytest.mark.asyncio
    async def test_the_login_still_knows_the_factor_is_on(
        self, mfa: MfaService, enrolled_user_id: int, rotated: None
    ) -> None:
        """Otherwise the password step itself would fail, for everybody."""
        assert await mfa.is_enabled(enrolled_user_id) is True

    @pytest.mark.asyncio
    async def test_the_settings_card_still_renders(
        self, mfa: MfaService, enrolled_user_id: int, rotated: None
    ) -> None:
        status = await mfa.status(enrolled_user_id)
        assert status.enabled is True
        assert status.recovery_codes_remaining == RECOVERY_CODE_COUNT

    @pytest.mark.asyncio
    async def test_the_escape_hatch_still_opens(
        self, mfa: MfaService, enrolled_user_id: int, rotated: None
    ) -> None:
        assert await mfa.disable_all() == 1
        assert await mfa.is_enabled(enrolled_user_id) is False

    @pytest.mark.asyncio
    async def test_an_enabled_factor_still_refuses_a_second_enrolment(
        self, mfa: MfaService, enrolled_user_id: int, rotated: None
    ) -> None:
        """The refusal is about state, and must not need the secret to say so."""
        with pytest.raises(ConflictError):
            await mfa.begin_enrolment(enrolled_user_id)


class TestNormaliseCode:
    def test_spaces_dashes_and_case_are_stripped(self) -> None:
        assert normalise_code(" abc-de 123 ") == "ABCDE123"


class TestConcurrentSubmits:
    """Two callers holding one code. The database decides, not a read-then-write.

    Each gets its own session, because that is the shape of the race: two
    tabs, two snapshots of the row, both taken before either one wrote.
    """

    @pytest.mark.asyncio
    async def test_one_totp_step_cannot_be_claimed_twice(
        self, mfa: MfaService, db_engine, user
    ) -> None:
        secret, _codes = await enrol(mfa, user.id)
        code = code_for(secret, offset_steps=1)

        factory = make_session_factory(db_engine)
        async with factory() as first, factory() as second:
            one, two = MfaService(first), MfaService(second)
            row_one, row_two = await one._row(user.id), await two._row(user.id)
            assert row_one is not None and row_two is not None
            counter_one = one._matching_counter(row_one, code)
            counter_two = two._matching_counter(row_two, code)
            assert counter_one is not None and counter_two == counter_one

            assert await one._claim_counter(row_one, counter_one) is True
            assert await two._claim_counter(row_two, counter_two) is False

    @pytest.mark.asyncio
    async def test_one_recovery_code_cannot_be_spent_twice(
        self, mfa: MfaService, db_engine, user
    ) -> None:
        _secret, codes = await enrol(mfa, user.id)

        factory = make_session_factory(db_engine)
        async with factory() as first, factory() as second:
            one, two = MfaService(first), MfaService(second)
            row_one, row_two = await one._row(user.id), await two._row(user.id)
            assert row_one is not None and row_two is not None
            index_one = one._find_recovery_code(row_one, codes[0])
            index_two = two._find_recovery_code(row_two, codes[0])
            assert index_one is not None and index_two == index_one

            assert await one._remove_recovery_code(row_one, index_one) is True
            assert await two._remove_recovery_code(row_two, index_two) is False

        status = await mfa.status(user.id)
        assert status.recovery_codes_remaining == RECOVERY_CODE_COUNT - 1


class TestConfirmingIsAClaim:
    """Two tabs confirming one pending enrolment. Only one set of codes is real."""

    @pytest.mark.asyncio
    async def test_the_second_confirmation_loses(self, mfa: MfaService, db_engine, user) -> None:
        enrolment = await mfa.begin_enrolment(user.id)
        code = code_for(enrolment.secret)

        factory = make_session_factory(db_engine)
        async with factory() as first, factory() as second:
            one, two = MfaService(first), MfaService(second)
            codes = await one.confirm_enrolment(user.id, code)
            with pytest.raises(ConflictError):
                await two.confirm_enrolment(user.id, code)

        # The codes the winning tab showed its user are the ones that work.
        assert await mfa.consume_recovery_code(user.id, codes[0]) is True


class TestReissuingIsAClaimToo:
    @pytest.mark.asyncio
    async def test_the_second_reissue_loses(self, mfa: MfaService, db_engine, user) -> None:
        """Both tabs would otherwise show ten codes and only one set would work."""
        await enrol(mfa, user.id)
        fresh = datetime.now(UTC)

        factory = make_session_factory(db_engine)
        async with factory() as first, factory() as second:
            one, two = MfaService(first), MfaService(second)
            # `two` read the set before `one` replaced it — which is the race.
            stale = await two._row(user.id)
            assert stale is not None
            codes = await one.regenerate_recovery_codes(user.id, mfa_verified_at=fresh)
            with pytest.raises(ConflictError):
                await two.regenerate_recovery_codes(user.id, mfa_verified_at=fresh)

        assert await mfa.consume_recovery_code(user.id, codes[0]) is True

    @pytest.mark.asyncio
    async def test_a_new_secret_cannot_gut_a_confirmed_factor(
        self, mfa: MfaService, db_engine, user
    ) -> None:
        """Set up racing a confirm would leave the factor on, with no way in."""
        enrolment = await mfa.begin_enrolment(user.id)
        code = code_for(enrolment.secret)

        factory = make_session_factory(db_engine)
        async with factory() as first, factory() as second:
            one, two = MfaService(first), MfaService(second)
            # `two` read the row while it was still unconfirmed.
            existing = await two._row(user.id)
            assert existing is not None and existing.enabled_at is None
            codes = await one.confirm_enrolment(user.id, code)
            with pytest.raises(ConflictError):
                await two.begin_enrolment(user.id)

        assert await mfa.is_enabled(user.id) is True
        assert await mfa.consume_recovery_code(user.id, codes[0]) is True
