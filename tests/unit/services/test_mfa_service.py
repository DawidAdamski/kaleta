# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for MfaService.

Covers: KAL-AUTH-013, KAL-AUTH-014, KAL-AUTH-015
"""

from __future__ import annotations

import json
import time

import pyotp
import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.db.types import FORMAT_AES_GCM
from kaleta.exceptions import ConflictError, ValidationError
from kaleta.models.user_mfa import UserMfa
from kaleta.services.auth_service import AuthService
from kaleta.services.mfa_service import (
    RECOVERY_CODE_COUNT,
    RECOVERY_CODE_LENGTH,
    TOTP_INTERVAL,
    MfaService,
    normalise_code,
)

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
        assert status.enrolment_started is True

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
        fresh = await mfa.regenerate_recovery_codes(user.id)
        assert set(fresh).isdisjoint(codes)
        assert await mfa.consume_recovery_code(user.id, codes[0]) is False
        assert await mfa.consume_recovery_code(user.id, fresh[0]) is True

    @pytest.mark.asyncio
    async def test_recovery_codes_need_mfa_to_be_on(self, mfa: MfaService, user) -> None:
        with pytest.raises(ValidationError):
            await mfa.regenerate_recovery_codes(user.id)


class TestDisable:
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


class TestNormaliseCode:
    def test_spaces_dashes_and_case_are_stripped(self) -> None:
        assert normalise_code(" abc-de 123 ") == "ABCDE123"
