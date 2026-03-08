from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.api.deps import PagedResponse, PaginationParams, get_session
from kaleta.models.transaction import TransactionType
from kaleta.schemas.transaction import TransactionCreate, TransactionResponse, TransactionUpdate
from kaleta.services.transaction_service import TransactionService

router = APIRouter(prefix="/transactions", tags=["Transactions"])


@router.get(
    "/",
    response_model=PagedResponse[TransactionResponse],
    summary="List transactions (paginated)",
)
async def list_transactions(
    account_ids: list[int] = Query(default=[], description="Filter by account IDs"),
    category_ids: list[int] = Query(default=[], description="Filter by category IDs"),
    date_from: datetime.date | None = Query(None, description="Start date (inclusive)"),
    date_to: datetime.date | None = Query(None, description="End date (inclusive)"),
    tx_types: list[TransactionType] = Query(
        default=[], alias="type", description="Filter by transaction types"
    ),
    search: str | None = Query(None, description="Search in description"),
    pagination: PaginationParams = Depends(),
    session: AsyncSession = Depends(get_session),
) -> PagedResponse[TransactionResponse]:
    svc = TransactionService(session)
    filters = dict(
        account_ids=account_ids or None,
        category_ids=category_ids or None,
        date_from=date_from,
        date_to=date_to,
        tx_types=tx_types or None,
        search=search,
    )
    items = await svc.list(**filters, limit=pagination.page_size, offset=pagination.offset)
    total = await svc.count(**filters)
    return PagedResponse.build(items, total, pagination)  # type: ignore[arg-type]


@router.post(
    "/", response_model=TransactionResponse, status_code=201, summary="Create a transaction"
)
async def create_transaction(
    data: TransactionCreate,
    session: AsyncSession = Depends(get_session),
) -> TransactionResponse:
    return await TransactionService(session).create(data)  # type: ignore[return-value]


@router.get(
    "/{transaction_id}", response_model=TransactionResponse, summary="Get transaction by ID"
)
async def get_transaction(
    transaction_id: int,
    session: AsyncSession = Depends(get_session),
) -> TransactionResponse:
    tx = await TransactionService(session).get(transaction_id)
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return tx  # type: ignore[return-value]


@router.put(
    "/{transaction_id}", response_model=TransactionResponse, summary="Update a transaction"
)
async def update_transaction(
    transaction_id: int,
    data: TransactionUpdate,
    session: AsyncSession = Depends(get_session),
) -> TransactionResponse:
    svc = TransactionService(session)
    if not await svc.get(transaction_id):
        raise HTTPException(status_code=404, detail="Transaction not found")
    updated = await svc.update(transaction_id, data)
    return updated  # type: ignore[return-value]


@router.delete("/{transaction_id}", status_code=204, summary="Delete a transaction")
async def delete_transaction(
    transaction_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    svc = TransactionService(session)
    if not await svc.get(transaction_id):
        raise HTTPException(status_code=404, detail="Transaction not found")
    await svc.delete(transaction_id)
