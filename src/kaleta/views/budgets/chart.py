"""Budget vs actual chart options."""

from __future__ import annotations

from typing import Any

from kaleta.i18n import t
from kaleta.views.chart_utils import apply_dark


def budget_chart_options(summaries: list[Any], is_dark: bool = False) -> dict[str, Any]:
    categories = [s.category_name for s in summaries]
    budgeted = [float(s.budget_amount) for s in summaries]
    actual = [float(s.actual_amount) for s in summaries]
    colors_act = ["#ef5350" if s.over_budget else "#4caf50" for s in summaries]

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
                "itemStyle": {"color": "#90caf9"},
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
