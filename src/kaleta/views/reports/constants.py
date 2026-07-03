"""Report builder field definitions."""

from __future__ import annotations

DIMENSIONS = [
    ("category", "reports.dim_category", "category"),
    ("account", "reports.dim_account", "account_balance_wallet"),
    ("month", "reports.dim_month", "calendar_month"),
    ("year", "reports.dim_year", "calendar_today"),
    ("type", "reports.dim_type", "swap_horiz"),
    ("institution", "reports.dim_institution", "account_balance"),
    ("weekday", "reports.dim_weekday", "today"),
]

METRICS = [
    ("sum", "reports.metric_sum", "functions"),
    ("count", "reports.metric_count", "tag"),
    ("avg", "reports.metric_avg", "percent"),
]

CHART_TYPES = [
    ("bar", "bar_chart"),
    ("line", "show_chart"),
    ("pie", "pie_chart"),
    ("donut", "donut_large"),
    ("table", "table_chart"),
]

DATE_PRESETS = [
    ("all_time", "reports.preset_all"),
    ("this_month", "reports.preset_this_month"),
    ("last_month", "reports.preset_last_month"),
    ("this_year", "reports.preset_this_year"),
    ("last_year", "reports.preset_last_year"),
    ("last_30", "reports.preset_last_30"),
    ("last_90", "reports.preset_last_90"),
    ("last_12_months", "reports.preset_last_12"),
    ("custom", "reports.preset_custom"),
]

TX_TYPES = [
    ("expense", "reports.type_expense", "trending_down", "negative"),
    ("income", "reports.type_income", "trending_up", "positive"),
    ("transfer", "reports.type_transfer", "swap_horiz", "primary"),
]

BUILDER_STATE_DEFAULTS: dict[str, object] = {
    "dimension": "category",
    "metric": "sum",
    "chart_type": "bar",
    "transaction_types": ["expense"],
    "date_preset": "this_year",
    "date_from": "",
    "date_to": "",
    "account_ids": [],
    "category_ids": [],
    "top_n": 10,
    "dragging": None,
    "dragging_grp": None,
    "result": None,
    "running": False,
    "error": None,
}
