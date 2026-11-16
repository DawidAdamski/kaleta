# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.api.deps import get_session
from kaleta.schemas.budget import (
    BudgetBulkUpsertRequest,
    BudgetCopyForwardRequest,
    BudgetCreate,
    BudgetRealizationResponse,
    BudgetRealizationRow,
    BudgetRealizationTotals,
    BudgetResponse,
    BudgetSummaryResponse,
    BudgetSummaryRow,
    BudgetUpdate,
    BudgetWriteCountResponse,
)
from kaleta.services.budget_service import BudgetService, RealizationTotals

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
    budgets = await BudgetService(session).list(month=month, year=year)
    return [BudgetResponse.model_validate(budget) for budget in budgets]


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
    return BudgetResponse.model_validate(await BudgetService(session).upsert(data))


@router.get(
    "/realization",
    response_model=BudgetRealizationResponse,
    summary="Budget realization for a month",
    description=(
        "Plan against actual expense, per category, for one month — the Budgets page's "
        "Realization tab. Rows run worst pace first (over, warning, on track). "
        "`as_of` (default today) sets how much of the month has elapsed. A category "
        "with spending but no plan has `used_pct` and `pace_delta` null and is `over`."
    ),
)
async def budget_realization(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    as_of: datetime.date | None = Query(None, description="Reference day; today if left out"),
    session: AsyncSession = Depends(get_session),
) -> BudgetRealizationResponse:
    day = as_of or datetime.date.today()
    rows = await BudgetService(session).realization_for_month(year, month, today=day)
    return BudgetRealizationResponse(
        year=year,
        month=month,
        as_of=day,
        totals=BudgetRealizationTotals.model_validate(RealizationTotals.of(rows)),
        categories=[BudgetRealizationRow.model_validate(row) for row in rows],
    )


@router.get(
    "/summary",
    response_model=BudgetSummaryResponse,
    summary="Budget against actual over a date range",
    description=(
        "Per expense category, by name: the budget and the spending between `start` and "
        "`end`, both inclusive. Budgets count whole months for every month the range "
        "touches; spending counts only the dates inside it."
    ),
    responses={422: {"description": "`end` before `start`"}},
)
async def budget_summary(
    start: datetime.date = Query(..., description="Range start (inclusive)"),
    end: datetime.date = Query(..., description="Range end (inclusive)"),
    session: AsyncSession = Depends(get_session),
) -> BudgetSummaryResponse:
    rows = await BudgetService(session).range_summary(start, end)
    return BudgetSummaryResponse(
        start=start, end=end, categories=[BudgetSummaryRow.model_validate(r) for r in rows]
    )


@router.post(
    "/copy-forward",
    response_model=BudgetWriteCountResponse,
    summary="Copy one month's budgets into another",
    description=(
        "Copies every budget row of the source month into the target month in one "
        "statement. Amounts the target already has are kept unless `overwrite` is true. "
        "`written` counts the rows created or updated."
    ),
)
async def copy_budgets_forward(
    data: BudgetCopyForwardRequest,
    session: AsyncSession = Depends(get_session),
) -> BudgetWriteCountResponse:
    written = await BudgetService(session).copy_forward(
        data.from_year, data.from_month, data.to_year, data.to_month, overwrite=data.overwrite
    )
    return BudgetWriteCountResponse(written=written)


@router.post(
    "/bulk",
    response_model=BudgetWriteCountResponse,
    summary="Create or update many budgets at once",
    description=(
        "Upserts up to 1000 entries in one statement, all or none. Entries sharing a "
        "category, month and year are summed, and `written` counts distinct keys. "
        "Every category must exist."
    ),
    responses={422: {"description": "An unknown category; nothing is written"}},
)
async def bulk_upsert_budgets(
    data: BudgetBulkUpsertRequest,
    session: AsyncSession = Depends(get_session),
) -> BudgetWriteCountResponse:
    return BudgetWriteCountResponse(written=await BudgetService(session).bulk_upsert(data.entries))


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
    return BudgetResponse.model_validate(budget)


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
    updated = await BudgetService(session).update(budget_id, data)
    if updated is None:
        raise HTTPException(status_code=404, detail="Budget entry not found")
    return BudgetResponse.model_validate(updated)


@router.delete("/{budget_id}", status_code=204, summary="Delete a budget entry", responses=_404)
async def delete_budget(
    budget_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    svc = BudgetService(session)
    if not await svc.get(budget_id):
        raise HTTPException(status_code=404, detail="Budget entry not found")
    await svc.delete(budget_id)
