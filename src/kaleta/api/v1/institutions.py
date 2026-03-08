from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.api.deps import get_session
from kaleta.schemas.institution import InstitutionCreate, InstitutionResponse, InstitutionUpdate
from kaleta.services.institution_service import InstitutionService

router = APIRouter(prefix="/institutions", tags=["Institutions"])


@router.get("/", response_model=list[InstitutionResponse], summary="List all institutions")
async def list_institutions(
    session: AsyncSession = Depends(get_session),
) -> list[InstitutionResponse]:
    return await InstitutionService(session).list()  # type: ignore[return-value]


@router.post(
    "/", response_model=InstitutionResponse, status_code=201, summary="Create an institution"
)
async def create_institution(
    data: InstitutionCreate,
    session: AsyncSession = Depends(get_session),
) -> InstitutionResponse:
    return await InstitutionService(session).create(data)  # type: ignore[return-value]


@router.get(
    "/{institution_id}", response_model=InstitutionResponse, summary="Get institution by ID"
)
async def get_institution(
    institution_id: int,
    session: AsyncSession = Depends(get_session),
) -> InstitutionResponse:
    institution = await InstitutionService(session).get(institution_id)
    if not institution:
        raise HTTPException(status_code=404, detail="Institution not found")
    return institution  # type: ignore[return-value]


@router.put(
    "/{institution_id}", response_model=InstitutionResponse, summary="Update an institution"
)
async def update_institution(
    institution_id: int,
    data: InstitutionUpdate,
    session: AsyncSession = Depends(get_session),
) -> InstitutionResponse:
    svc = InstitutionService(session)
    if not await svc.get(institution_id):
        raise HTTPException(status_code=404, detail="Institution not found")
    updated = await svc.update(institution_id, data)
    return updated  # type: ignore[return-value]


@router.delete("/{institution_id}", status_code=204, summary="Delete an institution")
async def delete_institution(
    institution_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    svc = InstitutionService(session)
    if not await svc.get(institution_id):
        raise HTTPException(status_code=404, detail="Institution not found")
    await svc.delete(institution_id)
