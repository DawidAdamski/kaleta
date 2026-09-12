# SPDX-License-Identifier: AGPL-3.0-or-later
"""Budget vs actual chart options."""

from __future__ import annotations

from typing import Any

from kaleta.i18n import t
from kaleta.views.chart_utils import (
    CHART_NEUTRAL_BAR,
    apply_dark,
    chart_expense_color,
    chart_income_color,
)


def budget_chart_options(summaries: list[Any], is_dark: bool = False) -> dict[str, Any]:
    categories = [s.category_name for s in summaries]
    budgeted = [float(s.budget_amount) for s in summaries]
    actual = [float(s.actual_amount) for s in summaries]
    over, under = chart_expense_color(is_dark), chart_income_color(is_dark)
    colors_act = [over if s.over_budget else under for s in summaries]

    opts = {
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "legend": {"data": [t("budgets.budgeted"), t("budgets.actual")], "bottom": 0},
        "grid": {"left": "3%", "right": "4%", "bottom": "12%", "containLabel": True},
        "xAxis": {"type": "value", "axisLabel": {"formatter": "{value} zł"}},
        "yAxis": {"type": "category", "data": categories, "inverse": True},
        "series": [
            {
                "name": t("budgets.budgeted"),
                "type": "bar",
                "data": budgeted,
                "itemStyle": {"color": CHART_NEUTRAL_BAR},
                "barGap": "0%",
            },
            {
                "name": t("budgets.actual"),
                "type": "bar",
                "data": [
                    {"value": v, "itemStyle": {"color": c}}
                    for v, c in zip(actual, colors_act, strict=True)
                ],
            },
        ],
    }
    return apply_dark(opts, is_dark)
