# SPDX-License-Identifier: AGPL-3.0-or-later
"""Auth status routes. Read-only: enrolment needs the UI."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.api.deps import get_current_user_id, get_session_configured
from kaleta.schemas.auth import MfaStatusResponse
from kaleta.services.mfa_service import MfaService

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.get(
    "/mfa",
    response_model=MfaStatusResponse,
    summary="Two-factor authentication status",
    description=(
        "Reports whether the authenticated user has a confirmed second factor. "
        "Enrolment, recovery codes and disabling all happen in the UI — a "
        "headless install can read this but cannot change it."
    ),
)
async def mfa_status(
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session_configured),
) -> MfaStatusResponse:
    status = await MfaService(session).status(user_id)
    return MfaStatusResponse(
        enabled=status.enabled,
        enabled_at=status.enabled_at,
        recovery_codes_remaining=status.recovery_codes_remaining,
    )
