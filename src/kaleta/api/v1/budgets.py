from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.api.deps import get_session
from kaleta.schemas.budget import BudgetCreate, BudgetResponse, BudgetUpdate
from kaleta.services.budget_service import BudgetService

_404: dict[int | str, dict[str, Any]] = {404: {"description": "Budget entry not found"}}

router = APIRouter(prefix="/budgets", tags=["Budgets"])


@router.get(
    "/",
    response_model=list[BudgetResponse],
    summary="List budgets",
    description=(
        "Returns all budget entries. Use `year` to filter by year, "
        "and `month` (1–12) together with `year` to narrow down to a specific month."
    ),
)
async def list_budgets(
    year: int | None = Query(None, description="Filter by year"),
    month: int | None = Query(None, ge=1, le=12, description="Filter by month (requires year)"),
    session: AsyncSession = Depends(get_session),
) -> list[BudgetResponse]:
    return await BudgetService(session).list(month=month, year=year)  # type: ignore[return-value]


@router.post(
    "/",
    response_model=BudgetResponse,
    status_code=201,
    summary="Create or update a budget entry",
    description=(
        "Upserts a budget for the given category + month + year. "
        "If an entry already exists it is updated in place. "
        "`amount` must be greater than 0. "
        "Note: always returns 201 regardless of whether a new entry was created or an existing one "
        "updated."
    ),
)
async def create_budget(
    data: BudgetCreate,
    session: AsyncSession = Depends(get_session),
) -> BudgetResponse:
    return await BudgetService(session).upsert(data)  # type: ignore[return-value]


@router.get(
    "/{budget_id}",
    response_model=BudgetResponse,
    summary="Get budget entry by ID",
    responses=_404,
)
async def get_budget(
    budget_id: int,
    session: AsyncSession = Depends(get_session),
) -> BudgetResponse:
    budget = await BudgetService(session).get(budget_id)
    if not budget:
        raise HTTPException(status_code=404, detail="Budget entry not found")
    return budget  # type: ignore[return-value]


@router.put(
    "/{budget_id}",
    response_model=BudgetResponse,
    summary="Update a budget entry",
    description=(
        "Partially updates a budget entry. "
        "`month` and `year` must always be provided together, or neither."
    ),
    responses=_404,
)
async def update_budget(
    budget_id: int,
    data: BudgetUpdate,
    session: AsyncSession = Depends(get_session),
) -> BudgetResponse:
    svc = BudgetService(session)
    if not await svc.get(budget_id):
        raise HTTPException(status_code=404, detail="Budget entry not found")
    updated = await svc.update(budget_id, data)
    return updated  # type: ignore[return-value]


@router.delete("/{budget_id}", status_code=204, summary="Delete a budget entry", responses=_404)
async def delete_budget(
    budget_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    svc = BudgetService(session)
    if not await svc.get(budget_id):
        raise HTTPException(status_code=404, detail="Budget entry not found")
    await svc.delete(budget_id)
