# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import hashlib
import re
import secrets
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.config import settings
from kaleta.db.tenant_context import current_tenant
from kaleta.exceptions import ValidationError
from kaleta.models.api_token import ApiToken
from kaleta.models.tenant import LocalIdentity, TenantMemberStatus
from kaleta.services.auth_service import PLACEHOLDER_USERNAME, AuthService
from kaleta.services.local_identity_service import subject_of
from kaleta.services.mfa_service import MfaService
from kaleta.services.tenant_service import TenantMembership, TenantService

_MIN_API_TOKEN_LENGTH = 16
MIN_API_TOKEN_LENGTH = _MIN_API_TOKEN_LENGTH
#: ``kt_<tenant id>_<secret>`` — a hosted token names its tenant, because the
#: token table lives inside the tenant's schema and has to be found first.
_TENANT_TOKEN_RE = re.compile(r"^kt_([1-9][0-9]{0,18})_([A-Za-z0-9_-]{16,})$")


def is_env_token(raw_token: str) -> bool:
    """Whether ``raw_token`` is ``KALETA_API_TOKEN`` (set, long enough, equal)."""
    env_token = settings.api_token
    if not env_token or len(env_token) < _MIN_API_TOKEN_LENGTH:
        return False
    if len(raw_token) < _MIN_API_TOKEN_LENGTH:
        return False
    # Bytes: `compare_digest` refuses a non-ASCII str with TypeError, and a
    # header is whatever the client sent (Starlette decodes it as latin-1).
    return secrets.compare_digest(raw_token.encode(), env_token.encode())


async def env_token_membership(public: AsyncSession) -> TenantMembership | None:
    """Whom ``KALETA_API_TOKEN`` acts as on the registry layout.

    The instance administrator — the oldest enabled one — in their family;
    ``None`` while there is no administrator, or they have not signed in yet
    (no family), or their membership is not active. Self-hosted, headless use:
    a hosted (Supabase) instance has no administrator login, so the variable
    authenticates no one there.

    "Oldest enabled" moves: disabling that administrator hands the token to
    the next one, and their family (``docs/deployment.md``).
    """
    result = await public.execute(
        select(LocalIdentity.id)
        .where(LocalIdentity.is_instance_admin.is_(True), LocalIdentity.disabled.is_(False))
        .order_by(LocalIdentity.id)
        .limit(1)
    )
    admin_id = result.scalar_one_or_none()
    if admin_id is None:
        return None
    membership = await TenantService(public).get_member_by_subject(subject_of(admin_id))
    if (
        membership is None
        or membership.member.user_id is None
        or membership.member.status is not TenantMemberStatus.ACTIVE
    ):
        return None
    return membership


class ApiTokenService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def generate_raw_token() -> str:
        """A new raw token; prefixed with its tenant in ``KALETA_TENANCY=multi``."""
        secret = secrets.token_urlsafe(32)
        if settings.tenancy != "multi":
            return secret
        ctx = current_tenant()
        if ctx is None:
            msg = "No tenant context to mint an API token for"
            raise ValidationError(msg)
        return f"kt_{ctx.tenant_id}_{secret}"

    @staticmethod
    def tenant_id_from_token(raw_token: str) -> int | None:
        """The tenant a ``kt_`` token names, or ``None`` for any other shape.

        Only routing: the whole token is still hashed and looked up inside
        that tenant's schema, so a forged prefix finds nothing.
        """
        match = _TENANT_TOKEN_RE.fullmatch(raw_token)
        return int(match.group(1)) if match else None

    @staticmethod
    def hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode()).hexdigest()

    async def create_token(
        self,
        *,
        user_id: int,
        label: str,
        mfa_verified_at: datetime | None = None,
    ) -> tuple[ApiToken, str]:
        label = label.strip()
        if not label:
            msg = "Label is required"
            raise ValidationError(msg)
        await self._require_step_up(user_id, mfa_verified_at=mfa_verified_at)
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

    async def revoke_all(self, *, user_id: int) -> int:
        """Revoke every live token of ``user_id`` (a disabled login); return how many.

        No step-up: the caller is the instance administrator acting on someone
        else's login, not the owner of the tokens.
        """
        result = await self.session.execute(
            select(ApiToken).where(ApiToken.user_id == user_id, ApiToken.revoked_at.is_(None))
        )
        tokens = list(result.scalars().all())
        now = datetime.now(UTC)
        for token in tokens:
            token.revoked_at = now
        await self.session.commit()
        return len(tokens)

    async def revoke_token(
        self,
        *,
        token_id: int,
        user_id: int,
        mfa_verified_at: datetime | None = None,
    ) -> ApiToken | None:
        await self._require_step_up(user_id, mfa_verified_at=mfa_verified_at)
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
        if not is_env_token(raw_token):
            return None
        if settings.tenancy == "multi":
            # `resolve_request_tenant` put the instance administrator's
            # family and member in the context (`env_token_membership`).
            ctx = current_tenant()
            return ctx.member_user_id if ctx is not None else None
        user = await AuthService(self.session).get_single_user()
        if user is None or user.username == PLACEHOLDER_USERNAME:
            return None
        return user.id

    async def _require_step_up(self, user_id: int, *, mfa_verified_at: datetime | None) -> None:
        """A bearer token outlives a session, so minting one is a second-factor act.

        MFA off: nothing to prove and nothing changes. MFA on: the caller says
        *when* the second factor was last proved and this service decides
        whether that is recent enough, so the window is not a number a view
        can talk its way around. The default is "never", so a caller that has
        never heard of step-up cannot skip it by accident.
        """
        mfa = MfaService(self.session)
        if not await mfa.is_enabled(user_id):
            return
        if mfa.step_up_is_fresh(mfa_verified_at):
            return
        msg = "Confirm with a two-factor code before changing API tokens."
        raise ValidationError(msg)

    async def _record_event(self, *, event: str, label: str) -> None:
        from kaleta.db.audit import record_token_event

        await record_token_event(self.session, event=event, label=label)
