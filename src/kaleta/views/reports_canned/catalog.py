"""Report library catalog — slug, i18n keys, icon, colour."""

from __future__ import annotations

REPORTS: list[tuple[str, str, str, str, str]] = [
    (
        "income-statement",
        "reports_lib.income_statement",
        "reports_lib.income_statement_desc",
        "receipt_long",
        "primary",
    ),
    ("cash-flow", "reports_lib.cash_flow", "reports_lib.cash_flow_desc", "waves", "blue-7"),
    (
        "budget-variance",
        "reports_lib.budget_variance",
        "reports_lib.budget_variance_desc",
        "rule",
        "orange-7",
    ),
    (
        "savings-rate",
        "reports_lib.savings_rate",
        "reports_lib.savings_rate_desc",
        "savings",
        "green-7",
    ),
    (
        "spending-by-category",
        "reports_lib.spending_by_category",
        "reports_lib.spending_by_category_desc",
        "donut_large",
        "purple-7",
    ),
    (
        "top-merchants",
        "reports_lib.top_merchants",
        "reports_lib.top_merchants_desc",
        "storefront",
        "teal-7",
    ),
    ("yoy", "reports_lib.yoy", "reports_lib.yoy_desc", "compare_arrows", "indigo-7"),
    ("ytd-summary", "reports_lib.ytd_summary", "reports_lib.ytd_summary_desc", "today", "cyan-7"),
    (
        "largest-transactions",
        "reports_lib.largest_transactions",
        "reports_lib.largest_transactions_desc",
        "format_list_numbered",
        "pink-7",
    ),
    (
        "net-worth-statement",
        "reports_lib.net_worth_statement",
        "reports_lib.net_worth_statement_desc",
        "account_balance",
        "deep-purple-7",
    ),
]
