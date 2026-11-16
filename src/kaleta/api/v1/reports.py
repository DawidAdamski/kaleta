# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.api.deps import get_session
from kaleta.exceptions import ValidationError
from kaleta.models.transaction import TransactionType
from kaleta.schemas.analysis import (
    BudgetVarianceResponse,
    BudgetVarianceRowResponse,
    CashflowMonthResponse,
    CategoryAmountResponse,
    CategoryShareResponse,
    IncomeStatementResponse,
    MerchantSpendResponse,
    MoneyFlowLinkResponse,
    MoneyFlowNodeResponse,
    MoneyFlowResponse,
    SafeToSpendResponse,
    SpendingByCategoryResponse,
    YoYComparisonResponse,
    YoYRowResponse,
    YTDSummaryResponse,
)
from kaleta.services.money_flow_service import FlowMode, MoneyFlowService
from kaleta.services.report_service import ReportService

#: The longest date range one spending or merchants report may cover.
MAX_REPORT_SPAN_DAYS = 366

_RANGE_422: dict[int | str, dict[str, Any]] = {
    422: {"description": f"`end` not after `start`, or a range over {MAX_REPORT_SPAN_DAYS} days"}
}

router = APIRouter(prefix="/reports", tags=["Reports"])


def _check_range(start: datetime.date, end: datetime.date) -> None:
    if end <= start:
        raise ValidationError("end must be after start")
    if (end - start).days > MAX_REPORT_SPAN_DAYS:
        raise ValidationError(f"The range may span at most {MAX_REPORT_SPAN_DAYS} days.")


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


@router.get(
    "/spending-by-category",
    response_model=SpendingByCategoryResponse,
    summary="Spending by category for a date range",
    description=(
        "Expense categories ranked by amount between `start` (inclusive) and `end` "
        "(exclusive), each with its share of the total. Transfers and loan-linked rows "
        "are left out; split rows count per line."
    ),
    responses=_RANGE_422,
)
async def report_spending_by_category(
    start: datetime.date = Query(..., description="Range start (inclusive)"),
    end: datetime.date = Query(..., description="Range end (exclusive)"),
    session: AsyncSession = Depends(get_session),
) -> SpendingByCategoryResponse:
    _check_range(start, end)
    report = await ReportService(session).spending_by_category(start, end)
    return SpendingByCategoryResponse(
        start=report.start,
        end=report.end,
        rows=[
            CategoryShareResponse(
                category=r.category, amount=r.amount, share_pct=report.share_pct(r.amount)
            )
            for r in report.rows
        ],
        total=report.total,
    )


@router.get(
    "/top-merchants",
    response_model=list[MerchantSpendResponse],
    summary="Top payees by spend for a date range",
    description=(
        "Payees ranked by expense total between `start` (inclusive) and `end` "
        "(exclusive). Only expense rows that have a payee count."
    ),
    responses=_RANGE_422,
)
async def report_top_merchants(
    start: datetime.date = Query(..., description="Range start (inclusive)"),
    end: datetime.date = Query(..., description="Range end (exclusive)"),
    limit: int = Query(20, ge=1, le=100, description="How many payees to return"),
    session: AsyncSession = Depends(get_session),
) -> list[MerchantSpendResponse]:
    _check_range(start, end)
    rows = await ReportService(session).top_merchants(start, end, limit)
    return [MerchantSpendResponse(name=r.name, amount=r.amount, count=r.count) for r in rows]


@router.get(
    "/budget-variance",
    response_model=BudgetVarianceResponse,
    summary="Budget vs actual for a calendar month",
    description=(
        "Every expense category with a budget or with spending that month, by actual "
        "spend. `variance` is planned minus actual (positive is under budget); a "
        "category without a budget has no `variance_pct` or `spent_pct`."
    ),
)
async def report_budget_variance(
    year: int = Query(..., ge=1970, le=2100),
    month: int = Query(..., ge=1, le=12),
    session: AsyncSession = Depends(get_session),
) -> BudgetVarianceResponse:
    report = await ReportService(session).budget_variance(year, month)
    return BudgetVarianceResponse(
        year=report.year,
        month=report.month,
        rows=[
            BudgetVarianceRowResponse(
                category=r.category,
                planned=r.planned,
                actual=r.actual,
                variance=r.variance,
                variance_pct=r.variance_pct,
                spent_pct=r.spent_pct,
                over_budget=r.over_budget,
            )
            for r in report.rows
        ],
        total_planned=report.total_planned,
        total_actual=report.total_actual,
    )


@router.get(
    "/ytd",
    response_model=YTDSummaryResponse,
    summary="Year-to-date summary",
    description=(
        "Income, expenses, net, savings rate and the ten largest expense categories "
        "for the year — up to today for the current year. Without `year`, this year."
    ),
)
async def report_ytd(
    year: int | None = Query(None, ge=1970, le=2100),
    session: AsyncSession = Depends(get_session),
) -> YTDSummaryResponse:
    report = await ReportService(session).ytd_summary(year)
    return YTDSummaryResponse(
        year=report.year,
        income=report.income,
        expenses=report.expenses,
        net=report.net,
        savings_rate_pct=report.savings_rate_pct,
        top_expense_categories=[
            CategoryAmountResponse(category=c.category, amount=c.amount)
            for c in report.top_expense_categories
        ],
    )


@router.get(
    "/yoy",
    response_model=YoYComparisonResponse,
    summary="Year-over-year comparison by month",
    description=(
        "Twelve rows, January to December: the year's monthly totals against the "
        "previous year's, on the `expense` or `income` basis."
    ),
    responses={422: {"description": "basis `transfer`"}},
)
async def report_yoy(
    year: int = Query(..., ge=1971, le=2100),
    basis: TransactionType = Query(TransactionType.EXPENSE),
    session: AsyncSession = Depends(get_session),
) -> YoYComparisonResponse:
    if basis == TransactionType.TRANSFER:
        raise ValidationError("basis must be expense or income")
    report = await ReportService(session).yoy_comparison(year, basis)
    return YoYComparisonResponse(
        year=report.year,
        basis=TransactionType(report.basis),
        rows=[
            YoYRowResponse(
                month=r.month,
                this_year=r.this_year,
                last_year=r.last_year,
                delta=r.delta,
                delta_pct=r.delta_pct,
            )
            for r in report.rows
        ],
        total_this_year=report.total_this_year,
        total_last_year=report.total_last_year,
        total_delta=report.total_delta,
    )


@router.get(
    "/safe-to-spend",
    response_model=SafeToSpendResponse,
    summary="Safe to spend this month",
    description=(
        "For the month `as_of` falls in (today by default): posted income, minus "
        "planned expenses and subscription charges still due from `as_of`, minus what "
        "is already spent — in total and per remaining day, today included."
    ),
)
async def report_safe_to_spend(
    as_of: datetime.date | None = Query(None, description="Reference day; today if left out"),
    session: AsyncSession = Depends(get_session),
) -> SafeToSpendResponse:
    report = await ReportService(session).safe_to_spend(today=as_of)
    return SafeToSpendResponse(
        as_of=report.today,
        income=report.income,
        committed=report.committed,
        spent=report.spent,
        free=report.free,
        days_left=report.days_left,
        per_day=report.per_day,
        trailing_avg_per_day=report.trailing_avg_per_day,
        spendable=report.spendable,
    )
