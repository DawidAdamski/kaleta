# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.api.deps import get_session
from kaleta.exceptions import ValidationError
from kaleta.schemas.analysis import (
    CashflowMonthResponse,
    CategoryAmountResponse,
    IncomeStatementResponse,
    MoneyFlowLinkResponse,
    MoneyFlowNodeResponse,
    MoneyFlowResponse,
)
from kaleta.services.money_flow_service import FlowMode, MoneyFlowService
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


@router.get(
    "/money-flow",
    response_model=MoneyFlowResponse,
    summary="Money-flow Sankey graph for a date range",
)
async def report_money_flow(
    start: datetime.date = Query(..., description="Range start (inclusive)"),
    end: datetime.date = Query(..., description="Range end (exclusive)"),
    top_n: int = Query(12, ge=0, le=100, description="Max categories per side; 0 keeps all"),
    depth: int = Query(1, ge=1, le=2, description="1=top-level, 2=expand expense children"),
    mode: str = Query("budget", pattern="^(budget|accounts)$"),
    session: AsyncSession = Depends(get_session),
) -> MoneyFlowResponse:
    if end <= start:
        raise ValidationError("end must be after start")
    flow_mode: FlowMode = "accounts" if mode == "accounts" else "budget"
    flow = await MoneyFlowService(session).build(
        start,
        end,
        top_n=None if top_n == 0 else top_n,
        depth=depth,
        mode=flow_mode,
    )
    return MoneyFlowResponse(
        nodes=[MoneyFlowNodeResponse(id=n.id, label=n.label, kind=n.kind) for n in flow.nodes],
        links=[
            MoneyFlowLinkResponse(source=lnk.source, target=lnk.target, amount=lnk.amount)
            for lnk in flow.links
        ],
        total_in=flow.total_in,
        total_out=flow.total_out,
        net=flow.net,
        total_transfers=flow.total_transfers,
        period_label=flow.period_label,
        mode=flow.mode,
    )
