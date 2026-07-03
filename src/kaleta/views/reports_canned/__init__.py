"""Canned financial reports — landing page + per-report sub-routes."""

from __future__ import annotations

from kaleta.views.reports_canned import (
    budget_variance,
    cash_flow,
    income_statement,
    landing,
    largest_transactions,
    net_worth_statement,
    savings_rate,
    spending_by_category,
    top_merchants,
    yoy,
    ytd_summary,
)


def register() -> None:
    landing.register()
    income_statement.register()
    cash_flow.register()
    budget_variance.register()
    savings_rate.register()
    spending_by_category.register()
    top_merchants.register()
    yoy.register()
    ytd_summary.register()
    largest_transactions.register()
    net_worth_statement.register()
