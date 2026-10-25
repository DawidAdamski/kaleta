# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.api.deps import get_session
from kaleta.schemas.institution import InstitutionCreate, InstitutionResponse, InstitutionUpdate
from kaleta.services.institution_service import InstitutionService

_404: dict[int | str, dict[str, Any]] = {404: {"description": "Institution not found"}}

router = APIRouter(prefix="/institutions", tags=["Institutions"])


@router.get("/", response_model=list[InstitutionResponse], summary="List all institutions")
async def list_institutions(
    session: AsyncSession = Depends(get_session),
) -> list[InstitutionResponse]:
    institutions = await InstitutionService(session).list()
    return [InstitutionResponse.model_validate(institution) for institution in institutions]


@router.post(
    "/",
    response_model=InstitutionResponse,
    status_code=201,
    summary="Create an institution",
    description=(
        "Creates a new institution (bank, brokerage, etc.). "
        "`color` accepts a hex color code (e.g. `#FF5733`). "
        "`website` is optional and must be at most 200 characters."
    ),
)
async def create_institution(
    data: InstitutionCreate,
    session: AsyncSession = Depends(get_session),
) -> InstitutionResponse:
    return InstitutionResponse.model_validate(await InstitutionService(session).create(data))


@router.get(
    "/{institution_id}",
    response_model=InstitutionResponse,
    summary="Get institution by ID",
    responses=_404,
)
async def get_institution(
    institution_id: int,
    session: AsyncSession = Depends(get_session),
) -> InstitutionResponse:
    institution = await InstitutionService(session).get(institution_id)
    if not institution:
        raise HTTPException(status_code=404, detail="Institution not found")
    return InstitutionResponse.model_validate(institution)


@router.get(
    "/{institution_id}/logo",
    summary="Fetch an institution's logo image",
    responses=_404,
    response_class=Response,
)
async def get_institution_logo(
    institution_id: int,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Stream the stored logo. ``get_session`` binds the family schema and the
    data key, so the deferred, encrypted blob decrypts for this request only.
    """
    logo = await InstitutionService(session).get_logo(institution_id)
    if logo is None:
        raise HTTPException(status_code=404, detail="Institution not found")
    content, mime = logo
    return Response(
        content=content,
        media_type=mime,
        headers={
            # Private: it is one family's data, never shared-cacheable.
            "Cache-Control": "private, max-age=300",
            # A logo may be an SVG. Sandbox the response so one opened as a
            # top-level navigation cannot run inline script against another
            # family member, even under a permissive page CSP.
            "Content-Security-Policy": "sandbox; default-src 'none'",
            "Content-Disposition": "inline",
        },
    )


@router.put(
    "/{institution_id}",
    response_model=InstitutionResponse,
    summary="Update an institution",
    description=(
        "Partially updates an institution. Only fields included in the request body are changed."
    ),
    responses=_404,
)
async def update_institution(
    institution_id: int,
    data: InstitutionUpdate,
    session: AsyncSession = Depends(get_session),
) -> InstitutionResponse:
    updated = await InstitutionService(session).update(institution_id, data)
    if updated is None:
        raise HTTPException(status_code=404, detail="Institution not found")
    return InstitutionResponse.model_validate(updated)


@router.delete(
    "/{institution_id}", status_code=204, summary="Delete an institution", responses=_404
)
async def delete_institution(
    institution_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    svc = InstitutionService(session)
    if not await svc.get(institution_id):
        raise HTTPException(status_code=404, detail="Institution not found")
    await svc.delete(institution_id)
