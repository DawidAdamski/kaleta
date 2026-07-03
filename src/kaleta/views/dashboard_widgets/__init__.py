"""Dashboard Command Center — widget catalog.

Each widget is a small, self-contained async function that reads its own
data slice (via the services layer) and renders a card. Widgets are laid
out in a unified 4-column CSS grid; each widget declares a
``default_size`` as ``(cols, rows)`` and an ``allowed_sizes`` tuple the
user can cycle through via the resize button in edit mode.

Users pick which widgets they want via the Customize dialog; order and
per-widget sizing are persisted in ``app.storage.user["dashboard_layout"]``.
"""

from __future__ import annotations

from kaleta.views.dashboard_widgets.layout import (
    LayoutEntry,
    default_layout,
    resolve_user_layout,
    resolve_user_widgets,
)
from kaleta.views.dashboard_widgets.registry import (
    DEFAULT_WIDGETS,
    WIDGETS,
    Widget,
    WidgetSize,
    cycle_size,
    register,
)

# Import widget modules to populate the registry.
from . import (  # noqa: F401
    budget_variance_month,
    cashflow_chart,
    credit_utilization,
    largest_transactions,
    month_expenses,
    month_income,
    month_net,
    net_worth,
    net_worth_trend,
    predicted_30d,
    quick_actions,
    recent_transactions,
    savings_rate_kpi,
    savings_rate_trend,
    top_merchants,
    total_balance,
    upcoming_planned,
    ytd_summary,
)

__all__ = [
    "DEFAULT_WIDGETS",
    "LayoutEntry",
    "WIDGETS",
    "Widget",
    "WidgetSize",
    "cycle_size",
    "default_layout",
    "register",
    "resolve_user_layout",
    "resolve_user_widgets",
]
