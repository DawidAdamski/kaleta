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

    @pytest.mark.asyncio
    async def test_env_token_authenticates_existing_user(
        self, tokens: ApiTokenService, user, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from kaleta.services import api_token_service as mod

        env = "bootstrap-token-16chars"
        monkeypatch.setattr(mod.settings, "api_token", env)
        assert await tokens.authenticate_bearer(env) == user.id

    @pytest.mark.asyncio
    async def test_env_token_rejected_when_mismatch(
        self, tokens: ApiTokenService, user, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from kaleta.services import api_token_service as mod

        monkeypatch.setattr(mod.settings, "api_token", "bootstrap-token-16chars")
        assert await tokens.authenticate_bearer("wrong-token-16chars!") is None

    @pytest.mark.asyncio
    async def test_env_token_rejected_when_no_user(
        self, tokens: ApiTokenService, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from kaleta.services import api_token_service as mod

        monkeypatch.setattr(mod.settings, "api_token", "bootstrap-token-16chars")
        assert await tokens.authenticate_bearer("bootstrap-token-16chars") is None

    @pytest.mark.asyncio
    async def test_env_token_after_bootstrap(
        self, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from kaleta.services import api_token_service as mod

        env = "bootstrap-token-16chars"
        monkeypatch.setattr(mod.settings, "api_token", env)
        auth = AuthService(session)
        user = await auth.ensure_api_bootstrap_user()
        tokens = ApiTokenService(session)
        assert await tokens.authenticate_bearer(env) == user.id
