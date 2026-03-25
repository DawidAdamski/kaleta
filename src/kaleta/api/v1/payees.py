from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.api.deps import get_session
from kaleta.schemas.payee import PayeeCreate, PayeeResponse, PayeeUpdate
from kaleta.services.payee_service import PayeeService

_404 = {404: {"description": "Payee not found"}}

router = APIRouter(prefix="/payees", tags=["Payees"])


@router.get("/", response_model=list[PayeeResponse], summary="List all payees")
async def list_payees(session: AsyncSession = Depends(get_session)) -> list[PayeeResponse]:
    return await PayeeService(session).list()  # type: ignore[return-value]


@router.post(
    "/",
    response_model=PayeeResponse,
    status_code=201,
    summary="Create a payee",
    description=(
        "Creates a new payee. `name` must be unique (case-sensitive). "
        "Payees are also created automatically during mBank CSV import."
    ),
)
async def create_payee(
    data: PayeeCreate,
    session: AsyncSession = Depends(get_session),
) -> PayeeResponse:
    return await PayeeService(session).create(data)  # type: ignore[return-value]


@router.get("/{payee_id}", response_model=PayeeResponse, summary="Get payee by ID", responses=_404)
async def get_payee(
    payee_id: int,
    session: AsyncSession = Depends(get_session),
) -> PayeeResponse:
    payee = await PayeeService(session).get(payee_id)
    if not payee:
        raise HTTPException(status_code=404, detail="Payee not found")
    return payee  # type: ignore[return-value]


@router.put(
    "/{payee_id}",
    response_model=PayeeResponse,
    summary="Update a payee",
    description="Partially updates a payee. Only fields included in the request body are changed.",
    responses=_404,
)
async def update_payee(
    payee_id: int,
    data: PayeeUpdate,
    session: AsyncSession = Depends(get_session),
) -> PayeeResponse:
    svc = PayeeService(session)
    if not await svc.get(payee_id):
        raise HTTPException(status_code=404, detail="Payee not found")
    updated = await svc.update(payee_id, data)
    return updated  # type: ignore[return-value]


@router.delete("/{payee_id}", status_code=204, summary="Delete a payee", responses=_404)
async def delete_payee(
    payee_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    svc = PayeeService(session)
    if not await svc.get(payee_id):
        raise HTTPException(status_code=404, detail="Payee not found")
    await svc.delete(payee_id)
