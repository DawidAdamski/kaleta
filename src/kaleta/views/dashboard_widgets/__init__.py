# SPDX-License-Identifier: AGPL-3.0-or-later
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
    migrate_legacy_kpis,
    resolve_user_layout,
    resolve_user_widgets,
)
from kaleta.views.dashboard_widgets.registry import (
    BAND_ORDER,
    DEFAULT_WIDGETS,
    LEGACY_KPI_WIDGETS,
    MERGED_KPI_WIDGETS,
    WIDGETS,
    Band,
    Widget,
    WidgetSize,
    bands_for_layout,
    cycle_size,
    register,
    selectable_widgets,
)

# Import widget modules to populate the registry.
from . import (  # noqa: F401
    balance_card,
    budget_variance_month,
    cashflow_chart,
    credit_utilization,
    largest_transactions,
    month_card,
    month_expenses,
    month_income,
    month_net,
    net_worth,
    net_worth_trend,
    predicted_30d,
    quick_actions,
    recent_transactions,
    safe_to_spend,
    savings_rate_kpi,
    savings_rate_trend,
    top_merchants,
    total_balance,
    upcoming_planned,
    wizard_actions,
    ytd_summary,
)

__all__ = [
    "BAND_ORDER",
    "DEFAULT_WIDGETS",
    "Band",
    "bands_for_layout",
    "LEGACY_KPI_WIDGETS",
    "MERGED_KPI_WIDGETS",
    "LayoutEntry",
    "WIDGETS",
    "Widget",
    "WidgetSize",
    "cycle_size",
    "selectable_widgets",
    "default_layout",
    "migrate_legacy_kpis",
    "register",
    "resolve_user_layout",
    "resolve_user_widgets",
]
