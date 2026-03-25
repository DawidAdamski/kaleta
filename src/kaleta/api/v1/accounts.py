from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.api.deps import get_session
from kaleta.schemas.account import AccountCreate, AccountResponse, AccountUpdate
from kaleta.services.account_service import AccountService

_404 = {404: {"description": "Account not found"}}

router = APIRouter(prefix="/accounts", tags=["Accounts"])


@router.get("/", response_model=list[AccountResponse], summary="List all accounts")
async def list_accounts(session: AsyncSession = Depends(get_session)) -> list[AccountResponse]:
    return await AccountService(session).list()  # type: ignore[return-value]


@router.post(
    "/",
    response_model=AccountResponse,
    status_code=201,
    summary="Create an account",
    description=(
        "Creates a new account. `currency` must be a 3-letter ISO 4217 code (e.g. `PLN`, `EUR`). "
        "`balance` sets the opening balance. "
        "`institution_id` is optional — link to an existing institution."
    ),
)
async def create_account(
    data: AccountCreate,
    session: AsyncSession = Depends(get_session),
) -> AccountResponse:
    return await AccountService(session).create(data)  # type: ignore[return-value]


@router.get(
    "/{account_id}",
    response_model=AccountResponse,
    summary="Get account by ID",
    responses=_404,
)
async def get_account(
    account_id: int,
    session: AsyncSession = Depends(get_session),
) -> AccountResponse:
    account = await AccountService(session).get(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account  # type: ignore[return-value]


@router.put(
    "/{account_id}",
    response_model=AccountResponse,
    summary="Update an account",
    description=(
        "Partially updates an account. Only fields included in the request body are changed."
    ),
    responses=_404,
)
async def update_account(
    account_id: int,
    data: AccountUpdate,
    session: AsyncSession = Depends(get_session),
) -> AccountResponse:
    svc = AccountService(session)
    if not await svc.get(account_id):
        raise HTTPException(status_code=404, detail="Account not found")
    updated = await svc.update(account_id, data)
    return updated  # type: ignore[return-value]


@router.delete("/{account_id}", status_code=204, summary="Delete an account", responses=_404)
async def delete_account(
    account_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    svc = AccountService(session)
    if not await svc.get(account_id):
        raise HTTPException(status_code=404, detail="Account not found")
    await svc.delete(account_id)
