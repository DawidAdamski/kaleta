# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sensitive actions ask for the second factor again.

Covers: KAL-AUTH-017
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import pyotp
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import ValidationError
from kaleta.models.user import User
from kaleta.services.api_token_service import ApiTokenService
from kaleta.services.mfa_service import (
    STEP_UP_WINDOW_MINUTES,
    TOTP_INTERVAL,
    MfaService,
)


@pytest.fixture
def user(suite_owner: User) -> User:
    return suite_owner


async def enrol(session: AsyncSession, user_id: int) -> str:
    mfa = MfaService(session)
    enrolment = await mfa.begin_enrolment(user_id)
    code = pyotp.TOTP(enrolment.secret, interval=TOTP_INTERVAL).at(int(time.time()))
    await mfa.confirm_enrolment(user_id, str(code))
    return enrolment.secret


@pytest.mark.asyncio
async def test_creating_an_api_token_needs_a_fresh_code(session: AsyncSession, user) -> None:
    """Covers: KAL-AUTH-017"""
    await enrol(session, user.id)
    tokens = ApiTokenService(session)

    with pytest.raises(ValidationError):
        await tokens.create_token(user_id=user.id, label="ci")
    assert await tokens.list_tokens(user_id=user.id) == []

    _token, raw = await tokens.create_token(
        user_id=user.id, label="ci", mfa_verified_at=datetime.now(UTC)
    )
    assert raw
    assert len(await tokens.list_tokens(user_id=user.id)) == 1


@pytest.mark.asyncio
async def test_revoking_an_api_token_needs_a_fresh_code(session: AsyncSession, user) -> None:
    """Covers: KAL-AUTH-017"""
    tokens = ApiTokenService(session)
    token, _raw = await tokens.create_token(user_id=user.id, label="ci")
    await enrol(session, user.id)

    with pytest.raises(ValidationError):
        await tokens.revoke_token(token_id=token.id, user_id=user.id)
    assert (await tokens.list_tokens(user_id=user.id))[0].is_active is True

    await tokens.revoke_token(token_id=token.id, user_id=user.id, mfa_verified_at=datetime.now(UTC))
    assert (await tokens.list_tokens(user_id=user.id))[0].is_active is False


@pytest.mark.asyncio
async def test_without_a_second_factor_nothing_is_asked(session: AsyncSession, user) -> None:
    """Covers: KAL-AUTH-017"""
    tokens = ApiTokenService(session)
    _token, raw = await tokens.create_token(user_id=user.id, label="ci")
    assert raw


@pytest.mark.asyncio
async def test_a_recovery_code_is_accepted_for_step_up(session: AsyncSession, user) -> None:
    """Covers: KAL-AUTH-017

    Someone whose authenticator is gone is exactly the person who needs to
    revoke a token, so the step-up prompt takes what the login prompt takes.
    """
    secret = await enrol(session, user.id)
    mfa = MfaService(session)
    codes = await mfa.regenerate_recovery_codes(user.id, mfa_verified_at=datetime.now(UTC))

    assert await mfa.verify_challenge(user.id, codes[0]) is True
    assert await mfa.verify_challenge(user.id, codes[0]) is False

    fresh = pyotp.TOTP(secret, interval=TOTP_INTERVAL).at(int(time.time()) + TOTP_INTERVAL)
    assert await mfa.verify_challenge(user.id, str(fresh)) is True


@pytest.mark.asyncio
async def test_a_stale_code_is_not_a_fresh_one(session: AsyncSession, user) -> None:
    """Covers: KAL-AUTH-017

    The 10-minute window is the service's to judge: a view that hands over a
    timestamp from an hour ago gets the same refusal as one that hands over
    nothing, rather than being trusted because it said so.

    The minutes below are the scenario's literal ten, not the constant the
    service reads: asking the code under test how wide its own window is
    would make this test agree with any answer it gave.
    """
    await enrol(session, user.id)
    tokens = ApiTokenService(session)
    assert STEP_UP_WINDOW_MINUTES == 10, "KAL-AUTH-017 says ten minutes"
    stale = datetime.now(UTC) - timedelta(minutes=11)

    with pytest.raises(ValidationError):
        await tokens.create_token(user_id=user.id, label="ci", mfa_verified_at=stale)

    fresh = datetime.now(UTC) - timedelta(minutes=9)
    _token, raw = await tokens.create_token(user_id=user.id, label="ci", mfa_verified_at=fresh)
    assert raw
