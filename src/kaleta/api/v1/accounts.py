# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.api.deps import get_session
from kaleta.schemas.account import AccountCreate, AccountResponse, AccountUpdate
from kaleta.services.account_service import AccountService

_404: dict[int | str, dict[str, Any]] = {404: {"description": "Account not found"}}

router = APIRouter(prefix="/accounts", tags=["Accounts"])


@router.get("/", response_model=list[AccountResponse], summary="List all accounts")
async def list_accounts(session: AsyncSession = Depends(get_session)) -> list[AccountResponse]:
    return await AccountService(session).list_responses()


@router.post(
    "/",
    response_model=AccountResponse,
    status_code=201,
    summary="Create an account",
    description=(
        "Creates a new account. `currency` must be a 3-letter ISO 4217 code (e.g. `PLN`, `EUR`). "
        "`balance` is the balance today; with no transactions yet it is also the opening "
        "balance. Afterwards the balance follows the account's transactions. "
        "`institution_id` is optional — link to an existing institution."
    ),
)
async def create_account(
    data: AccountCreate,
    session: AsyncSession = Depends(get_session),
) -> AccountResponse:
    svc = AccountService(session)
    created = await svc.create(data)
    response = await svc.get_response(created.id)
    if response is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return response


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
    account = await AccountService(session).get_response(account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


@router.put(
    "/{account_id}",
    response_model=AccountResponse,
    summary="Update an account",
    description=(
        "Partially updates an account. Only fields included in the request body are changed. "
        "`balance` sets the current balance: the opening balance moves so that it plus the "
        "account's transactions lands on it; no transaction is changed."
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
    await svc.update(account_id, data)
    response = await svc.get_response(account_id)
    if response is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return response


@router.delete("/{account_id}", status_code=204, summary="Delete an account", responses=_404)
async def delete_account(
    account_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    svc = AccountService(session)
    if not await svc.get(account_id):
        raise HTTPException(status_code=404, detail="Account not found")
    await svc.delete(account_id)
