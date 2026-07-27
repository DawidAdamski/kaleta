# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


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
