# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unauthenticated health probe."""

from __future__ import annotations

from fastapi import APIRouter, Depends, FastAPI, Response
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.api.deps import get_session
from kaleta.schemas.health import HealthResponse
from kaleta.services.health_service import HealthService

router = APIRouter(tags=["Health"])


async def _health_payload(
    response: Response,
    session: AsyncSession,
) -> HealthResponse:
    snapshot = await HealthService(session).check()
    if not snapshot.database_ok:
        response.status_code = 503
    return HealthResponse(
        status=snapshot.status,
        version=snapshot.version,
        database_ok=snapshot.database_ok,
        migrations_pending=snapshot.migrations_pending,
    )


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Unauthenticated health probe",
    description=(
        "Returns app version, database reachability, and whether Alembic migrations "
        "are pending. No authentication required. HTTP 503 when the database is unreachable."
    ),
    responses={503: {"description": "Database unreachable", "model": HealthResponse}},
)
async def health(
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> HealthResponse:
    return await _health_payload(response, session)


def register_health_alias(app: FastAPI) -> None:
    """Mount ``GET /health`` as an alias of ``/api/v1/health`` on a FastAPI app."""

    @app.get(
        "/health",
        response_model=HealthResponse,
        include_in_schema=False,
        summary="Health probe alias",
    )
    async def health_alias(
        response: Response,
        session: AsyncSession = Depends(get_session),
    ) -> HealthResponse:
        return await _health_payload(response, session)
