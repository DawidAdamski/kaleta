# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.api.deps import get_session
from kaleta.schemas.personal_loan import PersonalLoanResponse
from kaleta.services.personal_loan_service import PersonalLoanService

router = APIRouter(prefix="/personal-loans", tags=["Personal loans"])


@router.get("/", response_model=list[PersonalLoanResponse], summary="List personal loans")
async def list_personal_loans(
    session: AsyncSession = Depends(get_session),
) -> list[PersonalLoanResponse]:
    return await PersonalLoanService(session).list_loans()  # type: ignore[return-value]
