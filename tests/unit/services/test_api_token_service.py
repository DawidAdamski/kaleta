# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for ApiTokenService."""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.services.api_token_service import ApiTokenService
from kaleta.services.auth_service import AuthService


@pytest_asyncio.fixture
async def user(session: AsyncSession):
    return await AuthService(session).create_user("owner", "password-123")


@pytest.fixture
def tokens(session: AsyncSession) -> ApiTokenService:
    return ApiTokenService(session)


class TestApiTokenService:
    @pytest.mark.asyncio
    async def test_create_returns_raw_token_once(self, tokens: ApiTokenService, user) -> None:
        token, raw = await tokens.create_token(user_id=user.id, label="ci")
        assert raw
        assert token.label == "ci"
        assert token.token_hash == ApiTokenService.hash_token(raw)
        assert token.is_active

    @pytest.mark.asyncio
    async def test_authenticate_updates_last_used(self, tokens: ApiTokenService, user) -> None:
        token, raw = await tokens.create_token(user_id=user.id, label="ci")
        user_id = await tokens.authenticate_bearer(raw)
        assert user_id == user.id
        listed = await tokens.list_tokens(user_id=user.id)
        assert listed[0].last_used_at is not None

    @pytest.mark.asyncio
    async def test_revoked_token_rejected(self, tokens: ApiTokenService, user) -> None:
        token, raw = await tokens.create_token(user_id=user.id, label="ci")
        await tokens.revoke_token(token_id=token.id, user_id=user.id)
        assert await tokens.authenticate_bearer(raw) is None

    @pytest.mark.asyncio
    async def test_wrong_token_rejected(self, tokens: ApiTokenService, user) -> None:
        await tokens.create_token(user_id=user.id, label="ci")
        assert await tokens.authenticate_bearer("not-a-valid-token") is None

    @pytest.mark.asyncio
    async def test_short_token_rejected(self, tokens: ApiTokenService, user) -> None:
        assert await tokens.authenticate_bearer("short") is None
