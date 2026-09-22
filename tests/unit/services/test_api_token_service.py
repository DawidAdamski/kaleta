# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for ApiTokenService."""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import ValidationError
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


class TestStepUp:
    """A bearer token outlives a browser session, so minting one needs the code.

    Covers: KAL-AUTH-017
    """

    async def _enrol(self, session: AsyncSession, user_id: int) -> None:
        import time

        import pyotp

        from kaleta.services.mfa_service import TOTP_INTERVAL, MfaService

        mfa = MfaService(session)
        enrolment = await mfa.begin_enrolment(user_id)
        code = pyotp.TOTP(enrolment.secret, interval=TOTP_INTERVAL).at(int(time.time()))
        await mfa.confirm_enrolment(user_id, str(code))

    @pytest.mark.asyncio
    async def test_without_mfa_nothing_changes(self, tokens: ApiTokenService, user) -> None:
        _token, raw = await tokens.create_token(user_id=user.id, label="ci")
        assert raw

    @pytest.mark.asyncio
    async def test_with_mfa_creating_needs_a_fresh_code(
        self, tokens: ApiTokenService, session: AsyncSession, user
    ) -> None:
        await self._enrol(session, user.id)
        with pytest.raises(ValidationError):
            await tokens.create_token(user_id=user.id, label="ci")

    @pytest.mark.asyncio
    async def test_with_mfa_and_a_fresh_code_creating_works(
        self, tokens: ApiTokenService, session: AsyncSession, user
    ) -> None:
        await self._enrol(session, user.id)
        _token, raw = await tokens.create_token(user_id=user.id, label="ci", step_up_verified=True)
        assert raw

    @pytest.mark.asyncio
    async def test_with_mfa_revoking_needs_a_fresh_code(
        self, tokens: ApiTokenService, session: AsyncSession, user
    ) -> None:
        token, _raw = await tokens.create_token(user_id=user.id, label="ci")
        await self._enrol(session, user.id)
        with pytest.raises(ValidationError):
            await tokens.revoke_token(token_id=token.id, user_id=user.id)
        listed = await tokens.list_tokens(user_id=user.id)
        assert listed[0].is_active is True

    @pytest.mark.asyncio
    async def test_bearer_authentication_is_untouched_by_mfa(
        self, tokens: ApiTokenService, session: AsyncSession, user
    ) -> None:
        """An API token is its own credential; MFA guards minting it, not using it."""
        _token, raw = await tokens.create_token(user_id=user.id, label="ci")
        await self._enrol(session, user.id)
        assert await tokens.authenticate_bearer(raw) == user.id
