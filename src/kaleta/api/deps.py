# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import math
from collections.abc import AsyncGenerator
from contextlib import suppress
from dataclasses import replace
from typing import NoReturn, TypeVar

from fastapi import Depends, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.auth.session import authenticated_user_id, touch_session
from kaleta.config import settings
from kaleta.config.setup_config import is_configured
from kaleta.db import AsyncSessionFactory
from kaleta.db.tenant_context import TenantContext, current_tenant, set_tenant
from kaleta.exceptions import SetupRequiredError, UnauthorizedError
from kaleta.models.tenant import TenantStatus
from kaleta.services.api_token_service import ApiTokenService
from kaleta.services.tenant_service import TenantService

T = TypeVar("T")

_bearer_scheme = HTTPBearer(auto_error=False)
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


# ── Tenant (KALETA_TENANCY=multi) ─────────────────────────────────────────────


async def resolve_request_tenant(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> None:
    """Pick the tenant schema before any session for this request is opened.

    Every session dependency depends on this, and FastAPI runs it once per
    request, ahead of the first of them. A bearer token names its tenant in its
    prefix (``kt_<tenant>_<secret>``), so the schema is known before the token
    is hashed and looked up there; a cookie session carries its tenant.

    A request that presents a bearer token is judged by that token alone — no
    falling back to the cookie, which could belong to a different tenant than
    the one the token's prefix just picked. A request that resolves to no
    tenant is refused here with 401; were a route ever to open a session
    without passing through this, the session proxy refuses with a 500.
    """
    if settings.tenancy != "multi":
        return
    set_tenant(None)
    if credentials is not None and credentials.scheme.lower() == "bearer":
        tenant_id = ApiTokenService.tenant_id_from_token(credentials.credentials)
        if tenant_id is None:
            _unauthorized("Invalid API token")
        async with AsyncSessionFactory.public() as public:
            tenant = await TenantService(public).get_tenant(tenant_id)
        if tenant is None or tenant.status is not TenantStatus.ACTIVE:
            _unauthorized("Invalid API token")
        set_tenant(TenantContext(tenant_id=tenant.id, schema=tenant.schema_name))
        return
    # Sets the tenant from the cookie session (and says no to an expired or
    # revoked one) — the same call the cookie branch below repeats.
    if await authenticated_user_id(request) is None:
        _unauthorized()


# ── Database session ──────────────────────────────────────────────────────────


async def get_session(
    _tenant: None = Depends(resolve_request_tenant),
) -> AsyncGenerator[AsyncSession]:
    async with AsyncSessionFactory() as session:
        yield session


async def get_public_session() -> AsyncGenerator[AsyncSession]:
    """A session with no tenant schema — health probes and the registry."""
    async with AsyncSessionFactory.public() as session:
        yield session


async def get_session_configured(
    _tenant: None = Depends(resolve_request_tenant),
) -> AsyncGenerator[AsyncSession]:
    """Session for authenticated API routes — blocked until first-run setup completes."""
    if not is_configured():
        raise SetupRequiredError(
            "Complete first-run setup in the browser at /setup before using the API"
        )
    async with AsyncSessionFactory() as session:
        yield session


def _unauthorized(message: str = "Authentication required") -> NoReturn:
    raise UnauthorizedError(message)


async def require_setup() -> None:
    """Reject API use until first-run setup has written ``~/.kaleta/config.json``."""
    if not is_configured():
        raise SetupRequiredError(
            "Complete first-run setup in the browser at /setup before using the API"
        )


async def get_current_user_id(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    session: AsyncSession = Depends(get_session_configured),
) -> int:
    """Resolve the authenticated user from a bearer token or UI session cookie.

    Cookie (NiceGUI session) authentication is allowed only for safe HTTP methods.
    State-changing API calls require ``Authorization: Bearer``.
    """
    if credentials is not None and credentials.scheme.lower() == "bearer":
        user_id = await ApiTokenService(session).authenticate_bearer(credentials.credentials)
        if user_id is not None:
            ctx = current_tenant()
            if ctx is not None:
                # New rows this request creates are attributed to the token's owner.
                set_tenant(replace(ctx, member_user_id=user_id))
            return user_id
        if settings.tenancy == "multi":
            # `session` belongs to the tenant this token's prefix named; the
            # cookie, if any, may be somebody else's. See resolve_request_tenant.
            _unauthorized("Invalid API token")

    # Bearer tokens never reach this: they have their own revocation.
    session_user_id = await authenticated_user_id(request)
    if session_user_id is not None:
        if request.method.upper() in _SAFE_METHODS:
            # `authenticated_user_id` already ran the expiry check and bound
            # this request's storage; a rejected write below does not count
            # as activity. Recording activity is best-effort: NiceGUI reports
            # unusable storage as RuntimeError, KeyError or AssertionError —
            # the same set `authenticated_user_id` treats as "no session" — and
            # none of them may turn an accepted read into a 500.
            with suppress(RuntimeError, KeyError, AssertionError):
                touch_session()
            return session_user_id
        _unauthorized("Bearer token required for state-changing API requests")

    _unauthorized()


async def require_api_auth(user_id: int = Depends(get_current_user_id)) -> int:
    """Router-level dependency that enforces authentication on /api/v1/*."""
    return user_id


# ── Pagination ────────────────────────────────────────────────────────────────


class PaginationParams:
    def __init__(
        self,
        page: int = Query(1, ge=1, description="Page number (1-based)"),
        page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    ) -> None:
        self.page = page
        self.page_size = page_size
        self.offset = (page - 1) * page_size


class PagedResponse[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int

    @classmethod
    def build(cls, items: list[T], total: int, params: PaginationParams) -> PagedResponse[T]:
        return cls(
            items=items,
            total=total,
            page=params.page,
            page_size=params.page_size,
            pages=max(1, math.ceil(total / params.page_size)),
        )
