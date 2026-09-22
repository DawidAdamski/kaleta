# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sensitive actions ask for the second factor again.

Covers: KAL-AUTH-017
"""

from __future__ import annotations

import time

import pyotp
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import ValidationError
from kaleta.services.api_token_service import ApiTokenService
from kaleta.services.auth_service import AuthService
from kaleta.services.mfa_service import TOTP_INTERVAL, MfaService

PASSWORD = "owner-password-1"


@pytest_asyncio.fixture
async def user(session: AsyncSession):
    return await AuthService(session).create_user("owner", PASSWORD)


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

    _token, raw = await tokens.create_token(user_id=user.id, label="ci", step_up_verified=True)
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

    await tokens.revoke_token(token_id=token.id, user_id=user.id, step_up_verified=True)
    assert (await tokens.list_tokens(user_id=user.id))[0].is_active is False


@pytest.mark.asyncio
async def test_without_a_second_factor_nothing_is_asked(session: AsyncSession, user) -> None:
    """Covers: KAL-AUTH-017"""
    tokens = ApiTokenService(session)
    _token, raw = await tokens.create_token(user_id=user.id, label="ci")
    assert raw
