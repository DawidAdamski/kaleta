# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.config import settings
from kaleta.exceptions import ValidationError
from kaleta.models.api_token import ApiToken
from kaleta.services.auth_service import PLACEHOLDER_USERNAME, AuthService
from kaleta.services.mfa_service import MfaService

_MIN_API_TOKEN_LENGTH = 16
MIN_API_TOKEN_LENGTH = _MIN_API_TOKEN_LENGTH


class ApiTokenService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def generate_raw_token() -> str:
        return secrets.token_urlsafe(32)

    @staticmethod
    def hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode()).hexdigest()

    async def create_token(
        self,
        *,
        user_id: int,
        label: str,
        step_up_verified: bool = False,
    ) -> tuple[ApiToken, str]:
        label = label.strip()
        if not label:
            msg = "Label is required"
            raise ValidationError(msg)
        await self._require_step_up(user_id, step_up_verified=step_up_verified)
        raw_token = self.generate_raw_token()
        token = ApiToken(
            token_hash=self.hash_token(raw_token),
            label=label,
            user_id=user_id,
        )
        self.session.add(token)
        await self._record_event(event="token_create", label=label)
        await self.session.refresh(token)
        return token, raw_token

    async def list_tokens(self, *, user_id: int) -> list[ApiToken]:
        result = await self.session.execute(
            select(ApiToken).where(ApiToken.user_id == user_id).order_by(ApiToken.created_at.desc())
        )
        return list(result.scalars().all())

    async def revoke_token(
        self,
        *,
        token_id: int,
        user_id: int,
        step_up_verified: bool = False,
    ) -> ApiToken | None:
        await self._require_step_up(user_id, step_up_verified=step_up_verified)
        result = await self.session.execute(
            select(ApiToken).where(ApiToken.id == token_id, ApiToken.user_id == user_id)
        )
        token = result.scalar_one_or_none()
        if token is None or token.revoked_at is not None:
            return token
        token.revoked_at = datetime.now(UTC)
        await self._record_event(event="token_revoke", label=token.label)
        await self.session.refresh(token)
        return token

    async def authenticate_bearer(self, raw_token: str) -> int | None:
        if not raw_token or len(raw_token) < _MIN_API_TOKEN_LENGTH:
            return None
        token_hash = self.hash_token(raw_token)
        result = await self.session.execute(
            select(ApiToken).where(
                ApiToken.token_hash == token_hash,
                ApiToken.revoked_at.is_(None),
            )
        )
        token = result.scalar_one_or_none()
        if token is None:
            return await self._authenticate_env_token(raw_token)
        if not secrets.compare_digest(token.token_hash, token_hash):
            return None
        token.last_used_at = datetime.now(UTC)
        await self.session.commit()
        return token.user_id

    async def _authenticate_env_token(self, raw_token: str) -> int | None:
        env_token = settings.api_token
        if not env_token or len(env_token) < _MIN_API_TOKEN_LENGTH:
            return None
        if len(raw_token) < _MIN_API_TOKEN_LENGTH:
            return None
        if not secrets.compare_digest(raw_token, env_token):
            return None
        user = await AuthService(self.session).get_single_user()
        if user is None or user.username == PLACEHOLDER_USERNAME:
            return None
        return user.id

    async def _require_step_up(self, user_id: int, *, step_up_verified: bool) -> None:
        """A bearer token outlives a session, so minting one is a second-factor act.

        MFA off: nothing to prove and nothing changes. MFA on: the caller must
        say the code was given recently — the default is "it was not", so a
        caller that has never heard of step-up cannot skip it by accident.
        """
        if step_up_verified:
            return
        if await MfaService(self.session).is_enabled(user_id):
            msg = "Confirm with a two-factor code before changing API tokens."
            raise ValidationError(msg)

    async def _record_event(self, *, event: str, label: str) -> None:
        from kaleta.db.audit import record_token_event

        await record_token_event(self.session, event=event, label=label)
