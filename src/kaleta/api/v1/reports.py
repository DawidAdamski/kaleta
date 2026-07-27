# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.api.deps import get_session
from kaleta.schemas.analysis import (
    CashflowMonthResponse,
    CategoryAmountResponse,
    IncomeStatementResponse,
)
from kaleta.services.report_service import ReportService

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get(
    "/cashflow",
    response_model=list[CashflowMonthResponse],
    summary="Cashflow for the last N months",
)
async def report_cashflow(
    months: int = Query(6, ge=1, le=60, description="Number of months including current"),
    session: AsyncSession = Depends(get_session),
) -> list[CashflowMonthResponse]:
    rows = await ReportService(session).cashflow_last_n_months(months)
    return [
        CashflowMonthResponse(
            year=row.year,
            month=row.month,
            income=row.income,
            expenses=row.expenses,
            net=row.net,
            label=row.label,
        )
        for row in rows
    ]


@router.get(
    "/income-statement",
    response_model=IncomeStatementResponse,
    summary="Income statement for a calendar month",
)
async def report_income_statement(
    year: int = Query(..., ge=1970, le=2100),
    month: int = Query(..., ge=1, le=12),
    session: AsyncSession = Depends(get_session),
) -> IncomeStatementResponse:
    stmt = await ReportService(session).income_statement(year, month)
    return IncomeStatementResponse(
        year=stmt.year,
        month=stmt.month,
        income_by_category=[
            CategoryAmountResponse(category=c.category, amount=c.amount)
            for c in stmt.income_by_category
        ],
        expense_by_category=[
            CategoryAmountResponse(category=c.category, amount=c.amount)
            for c in stmt.expense_by_category
        ],
        total_income=stmt.total_income,
        total_expenses=stmt.total_expenses,
        net=stmt.net_income,
    )
