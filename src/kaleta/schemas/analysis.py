# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from kaleta.models.transaction import TransactionType


class NetWorthSnapshotResponse(BaseModel):
    """Current net-worth totals for headless analysis."""

    model_config = ConfigDict(from_attributes=True)

    total_assets: Decimal
    total_liabilities: Decimal
    net_worth: Decimal
    default_currency: str
    prev_month_net_worth: Decimal | None = None
    has_unknown_rates: bool = False


class CashflowMonthResponse(BaseModel):
    year: int
    month: int
    income: Decimal
    expenses: Decimal
    net: Decimal
    label: str


class CategoryAmountResponse(BaseModel):
    category: str
    amount: Decimal


class IncomeStatementResponse(BaseModel):
    year: int
    month: int
    income_by_category: list[CategoryAmountResponse] = Field(default_factory=list)
    expense_by_category: list[CategoryAmountResponse] = Field(default_factory=list)
    total_income: Decimal
    total_expenses: Decimal
    net: Decimal


class MoneyFlowNodeResponse(BaseModel):
    id: str
    label: str
    kind: str


class MoneyFlowLinkResponse(BaseModel):
    source: str
    target: str
    amount: Decimal


class MoneyFlowResponse(BaseModel):
    nodes: list[MoneyFlowNodeResponse] = Field(default_factory=list)
    links: list[MoneyFlowLinkResponse] = Field(default_factory=list)
    total_in: Decimal
    total_out: Decimal
    net: Decimal
    total_transfers: Decimal = Decimal("0")
    period_label: str
    mode: str = "budget"


class CategoryShareResponse(BaseModel):
    category: str
    amount: Decimal
    #: This category's share of the period's total spend, 0–100, unrounded.
    share_pct: Decimal


class SpendingByCategoryResponse(BaseModel):
    start: datetime.date
    end: datetime.date
    rows: list[CategoryShareResponse]
    total: Decimal


class MerchantSpendResponse(BaseModel):
    name: str
    amount: Decimal
    count: int


class BudgetVarianceRowResponse(BaseModel):
    category: str
    planned: Decimal
    actual: Decimal
    #: Planned minus actual: positive is under budget.
    variance: Decimal
    variance_pct: Decimal | None
    #: Actual as a percentage of planned; 115 means 15% over.
    spent_pct: Decimal | None
    over_budget: bool


class BudgetVarianceResponse(BaseModel):
    year: int
    month: int
    rows: list[BudgetVarianceRowResponse]
    total_planned: Decimal
    total_actual: Decimal


class YTDSummaryResponse(BaseModel):
    year: int
    income: Decimal
    expenses: Decimal
    net: Decimal
    savings_rate_pct: Decimal | None
    top_expense_categories: list[CategoryAmountResponse]


class YoYRowResponse(BaseModel):
    month: int
    this_year: Decimal
    last_year: Decimal
    delta: Decimal
    delta_pct: Decimal | None


class YoYComparisonResponse(BaseModel):
    year: int
    basis: TransactionType
    rows: list[YoYRowResponse]
    total_this_year: Decimal
    total_last_year: Decimal
    total_delta: Decimal


class SafeToSpendResponse(BaseModel):
    as_of: datetime.date
    income: Decimal
    committed: Decimal
    spent: Decimal
    free: Decimal
    days_left: int
    per_day: Decimal
    trailing_avg_per_day: Decimal
    spendable: bool
