# SPDX-License-Identifier: AGPL-3.0-or-later
"""Health probe with tiered disclosure (KAL-SEC-001, security assessment F-1).

The probe answers three audiences. An unauthenticated caller — a monitor — gets
only liveness (``status`` + ``database_ok``). A signed-in caller (a family bearer
token, or a UI cookie session) additionally gets the version, the sign-in backend
and whether migrations are pending. Only an *instance-level* credential — the
``KALETA_API_TOKEN`` env token, or a cookie session the registry confirms is an
instance administrator — gets the cross-family operational state (the pending
count, the keyring-session count and the suspended-family ids).

A family-scoped credential never reaches the admin tier, so no family can read
another family's operational state. The resolver never raises: a probe must
answer 200/503, never 401, so a bad or unknown credential is treated as public.
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, FastAPI, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.api.deps import get_public_session
from kaleta.auth.session import authenticated_user_id, session_tenant
from kaleta.config import settings
from kaleta.db import AsyncSessionFactory
from kaleta.db.tenant_context import TenantContext, set_tenant
from kaleta.models.tenant import TenantStatus
from kaleta.schemas.health import HealthResponse
from kaleta.services.api_token_service import ApiTokenService, is_env_token
from kaleta.services.health_service import HealthService
from kaleta.services.instance_admin_service import is_instance_admin
from kaleta.services.tenant_service import TenantService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])

HealthAudience = Literal["public", "family", "admin"]

_bearer_scheme = HTTPBearer(auto_error=False)

_HEALTH_DESCRIPTION = (
    "Database reachability and app health, disclosed by tier. Unauthenticated "
    "callers get only `status` and `database_ok` (HTTP 503 when the database is "
    "unreachable). A signed-in caller also gets the version, the sign-in backend "
    "and whether migrations are pending. Only an instance administrator (the "
    "`KALETA_API_TOKEN` env token, or an admin cookie session) gets the "
    "cross-family state: the pending-migration count, the keyring-session count "
    "and the suspended-family ids. No authentication required for liveness."
)


async def health_audience(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> HealthAudience:
    """How much of the probe this caller may see — never raises.

    A family bearer token or a signed-in cookie session is ``family``; only an
    instance-level credential (the env token, or a cookie session the registry
    confirms as an instance administrator) is ``admin``. A family-scoped
    credential never reaches ``admin``.

    Any failure resolving the tier — a database that is down, an unconfigured
    factory — falls back to ``public`` rather than propagating: a probe must
    answer 200/503, never 500, so ``_health_payload`` can still map an
    unreachable database to 503.
    """
    try:
        if credentials is not None and credentials.scheme.lower() == "bearer":
            return await _bearer_audience(credentials.credentials)
        return await _cookie_audience(request)
    except Exception:
        logger.exception("Health probe: could not resolve the caller's tier; treating as public")
        return "public"


async def _bearer_audience(token: str) -> HealthAudience:
    """The env token is the instance administrator; a family token is family tier."""
    if is_env_token(token):
        return "admin"
    tenant_id = ApiTokenService.tenant_id_from_token(token)
    if tenant_id is None:
        return "public"
    async with AsyncSessionFactory.public() as public:
        tenant = await TenantService(public).get_tenant(tenant_id)
    if tenant is None or tenant.status is not TenantStatus.ACTIVE:
        return "public"
    # Bind the token's family so its ApiToken row can be looked up in that schema.
    set_tenant(TenantContext(tenant_id=tenant.id, schema=tenant.schema_name))
    async with AsyncSessionFactory() as session:
        user_id = await ApiTokenService(session).authenticate_bearer(token)
    return "family" if user_id is not None else "public"


async def _cookie_audience(request: Request) -> HealthAudience:
    """A signed-in session is family tier; an instance admin (per the registry) is admin."""
    if await authenticated_user_id(request) is None:
        return "public"
    tenant = session_tenant()
    if tenant is not None:
        async with AsyncSessionFactory.public() as public:
            is_admin = await is_instance_admin(
                public,
                subject=tenant.auth_subject,
                email=tenant.email,
                auth_backend=settings.auth_backend,
                admin_emails=settings.instance_admin_emails,
            )
        if is_admin:
            return "admin"
    return "family"


async def _health_payload(
    response: Response,
    session: AsyncSession,
    audience: HealthAudience,
) -> HealthResponse:
    snapshot = await HealthService(session).check(
        include_family=audience in ("family", "admin"),
        include_admin=audience == "admin",
    )
    if not snapshot.database_ok:
        response.status_code = 503
    return HealthResponse(
        status=snapshot.status,
        database_ok=snapshot.database_ok,
        version=snapshot.version,
        migrations_pending=snapshot.migrations_pending,
        tenants_pending_migration=snapshot.tenants_pending_migration,
        auth_backend=snapshot.auth_backend,
        keyring_sessions=snapshot.keyring_sessions,
        suspended_tenants=snapshot.suspended_tenants,
    )


@router.get(
    "/health",
    response_model=HealthResponse,
    response_model_exclude_none=True,
    summary="Health probe (tiered disclosure)",
    description=_HEALTH_DESCRIPTION,
    responses={503: {"description": "Database unreachable", "model": HealthResponse}},
)
async def health(
    response: Response,
    audience: HealthAudience = Depends(health_audience),
    session: AsyncSession = Depends(get_public_session),
) -> HealthResponse:
    return await _health_payload(response, session, audience)


def register_health_alias(app: FastAPI) -> None:
    """Mount ``GET /health`` as an alias of ``/api/v1/health`` on a FastAPI app."""

    @app.get(
        "/health",
        response_model=HealthResponse,
        response_model_exclude_none=True,
        include_in_schema=False,
        summary="Health probe alias",
    )
    async def health_alias(
        response: Response,
        audience: HealthAudience = Depends(health_audience),
        session: AsyncSession = Depends(get_public_session),
    ) -> HealthResponse:
        return await _health_payload(response, session, audience)
