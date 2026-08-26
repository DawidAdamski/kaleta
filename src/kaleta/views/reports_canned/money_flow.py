# SPDX-License-Identifier: AGPL-3.0-or-later
"""Money-flow Sankey report — income → budget → expenses."""

from __future__ import annotations

import datetime
from typing import Any

from nicegui import app, ui

from kaleta.i18n import t
from kaleta.services import with_session
from kaleta.services.money_flow_service import (
    FlowMode,
    MoneyFlow,
    MoneyFlowLabels,
    MoneyFlowService,
    inclusive_end_exclusive,
    month_bounds,
    year_bounds,
)
from kaleta.views.chart_utils import CHART_EXPENSE, CHART_INCOME, CHART_TEAL, apply_dark
from kaleta.views.components.empty_state import report_no_data_label
from kaleta.views.layout import page_layout
from kaleta.views.reports_canned.formatters import csv_download, fmt
from kaleta.views.reports_canned.scaffold import (
    date_range_controls,
    export_button,
    kpi,
    loading_label,
    month_controls,
    report_header,
)
from kaleta.views.theme import SECTION_CARD, SECTION_TITLE

_PERIOD_MONTH = "month"
_PERIOD_YEAR = "year"
_PERIOD_CUSTOM = "custom"


def register() -> None:
    @ui.page("/reports/money-flow")
    async def page() -> None:
        is_dark: bool = app.storage.user.get("dark_mode", False)
        today = datetime.date.today()
        state: dict[str, Any] = {
            "period_mode": _PERIOD_MONTH,
            "year": today.year,
            "month": today.month,
            "start": today.replace(day=1).isoformat(),
            "end": today.isoformat(),
            "top_n": 12,
            "depth": 1,
            "view_mode": "budget",
            "data": None,
        }

        with page_layout(t("reports_lib.money_flow")):
            report_header(t("reports_lib.money_flow"), t("reports_lib.money_flow_desc"))

            def _labels() -> MoneyFlowLabels:
                return MoneyFlowLabels(
                    pool=t("money_flow.budget"),
                    surplus=t("money_flow.surplus"),
                    deficit=t("money_flow.deficit"),
                    other=t("money_flow.other"),
                    uncategorised=t("money_flow.uncategorised"),
                    income_suffix=t("money_flow.income_suffix"),
                    expense_suffix=t("money_flow.expense_suffix"),
                )

            def _bounds() -> tuple[datetime.date, datetime.date]:
                mode = state["period_mode"]
                if mode == _PERIOD_YEAR:
                    return year_bounds(int(state["year"]))
                if mode == _PERIOD_CUSTOM:
                    start = datetime.date.fromisoformat(state["start"])
                    end_incl = datetime.date.fromisoformat(state["end"])
                    return start, inclusive_end_exclusive(end_incl)
                return month_bounds(int(state["year"]), int(state["month"]))

            async def _load() -> None:
                start, end = _bounds()
                top_raw = state["top_n"]
                top_n: int | None = None if top_raw == "all" else int(top_raw)
                view_mode: FlowMode = "accounts" if state["view_mode"] == "accounts" else "budget"

                async def _fetch(session: Any) -> MoneyFlow:
                    return await MoneyFlowService(session).build(
                        start,
                        end,
                        top_n=top_n,
                        depth=int(state["depth"]),
                        mode=view_mode,
                        labels=_labels(),
                    )

                state["data"] = await with_session(_fetch)
                output.refresh()

            def _reload() -> None:
                ui.timer(0.01, _load, once=True)

            def _set_period_mode(e: Any) -> None:
                state["period_mode"] = e.value
                period_zone.refresh()
                _reload()

            def _set_view_mode(e: Any) -> None:
                state["view_mode"] = e.value
                _reload()

            def _set_depth(e: Any) -> None:
                state["depth"] = int(e.value)
                _reload()

            def _set_top_n(e: Any) -> None:
                state["top_n"] = e.value
                _reload()

            def _set_year(e: Any) -> None:
                state["year"] = int(e.value)
                _reload()

            with ui.row().classes("items-end gap-3 mb-2 flex-wrap"):
                ui.select(
                    {
                        "budget": t("money_flow.view_budget"),
                        "accounts": t("money_flow.view_accounts"),
                    },
                    label=t("money_flow.view"),
                    value=state["view_mode"],
                    on_change=_set_view_mode,
                ).classes("w-44")
                ui.select(
                    {
                        _PERIOD_MONTH: t("money_flow.period_month"),
                        _PERIOD_YEAR: t("money_flow.period_year"),
                        _PERIOD_CUSTOM: t("money_flow.period_custom"),
                    },
                    label=t("money_flow.period"),
                    value=state["period_mode"],
                    on_change=_set_period_mode,
                ).classes("w-40")
                ui.select(
                    {1: t("money_flow.depth_top"), 2: t("money_flow.depth_expand")},
                    label=t("money_flow.depth"),
                    value=state["depth"],
                    on_change=_set_depth,
                ).classes("w-52")
                ui.select(
                    {
                        8: "8",
                        12: "12",
                        20: "20",
                        "all": t("money_flow.top_n_all"),
                    },
                    label=t("money_flow.top_n"),
                    value=state["top_n"],
                    on_change=_set_top_n,
                ).classes("w-36")

            @ui.refreshable
            def period_zone() -> None:
                mode = state["period_mode"]
                if mode == _PERIOD_MONTH:
                    month_controls(state, _reload)
                elif mode == _PERIOD_YEAR:
                    today_y = datetime.date.today().year
                    years = {y: str(y) for y in range(today_y - 5, today_y + 1)}
                    with ui.row().classes("items-end gap-3 mb-2"):
                        ui.select(
                            years,
                            label=t("common.year"),
                            value=state["year"],
                            on_change=_set_year,
                        ).classes("w-32")
                else:
                    date_range_controls(state, _reload)

            period_zone()

            @ui.refreshable
            def output() -> None:
                flow: MoneyFlow | None = state["data"]
                if flow is None:
                    loading_label()
                    return
                if not flow.nodes:
                    report_no_data_label()
                    return

                net_label = t("money_flow.surplus") if flow.net >= 0 else t("money_flow.deficit")
                with ui.row().classes("w-full gap-3 flex-wrap mb-3"):
                    kpi(t("reports_lib.total_income"), fmt(flow.total_in), "south_west", "green-7")
                    kpi(
                        t("reports_lib.total_expenses"),
                        fmt(flow.total_out),
                        "north_east",
                        "red-7",
                    )
                    kpi(
                        net_label,
                        fmt(abs(flow.net)),
                        "savings" if flow.net >= 0 else "account_balance_wallet",
                        "green-7" if flow.net >= 0 else "orange-7",
                    )
                    if flow.total_transfers > 0:
                        kpi(
                            t("money_flow.transfers"),
                            fmt(flow.total_transfers),
                            "swap_horiz",
                            "teal-7",
                        )

                # NiceGUI serialises options as JSON — JS function strings are NOT
                # evaluated. Use human-readable unique labels as ECharts node names.
                id_to_label = {n.id: n.label for n in flow.nodes}
                node_data = [
                    {
                        "name": n.label,
                        "itemStyle": {"color": _node_color(n.kind)},
                    }
                    for n in flow.nodes
                ]
                link_data = [
                    {
                        "source": id_to_label[lnk.source],
                        "target": id_to_label[lnk.target],
                        "value": float(lnk.amount),
                        "lineStyle": {
                            "color": {
                                "type": "linear",
                                "x": 0,
                                "y": 0,
                                "x2": 1,
                                "y2": 0,
                                "colorStops": [
                                    {
                                        "offset": 0,
                                        "color": _link_color(lnk.source, flow),
                                    },
                                    {
                                        "offset": 1,
                                        "color": _link_color(lnk.target, flow),
                                    },
                                ],
                            },
                            "opacity": 0.45,
                        },
                    }
                    for lnk in flow.links
                ]

                with ui.card().classes(SECTION_CARD):
                    ui.label(t("money_flow.chart_title", period=flow.period_label)).classes(
                        SECTION_TITLE
                    )
                    ui.echart(
                        apply_dark(
                            {
                                "tooltip": {
                                    "trigger": "item",
                                    "formatter": "{b}: {c}",
                                },
                                "series": [
                                    {
                                        "type": "sankey",
                                        "emphasis": {"focus": "adjacency"},
                                        "nodeAlign": "justify",
                                        "lineStyle": {"curveness": 0.5},
                                        "label": {
                                            "color": "#94a3b8" if is_dark else "#334155",
                                        },
                                        "data": node_data,
                                        "links": link_data,
                                    }
                                ],
                            },
                            is_dark,
                        )
                    ).classes("w-full").style("height: 520px")

                def _export() -> None:
                    rows = [
                        [
                            id_to_label.get(lnk.source, lnk.source),
                            id_to_label.get(lnk.target, lnk.target),
                            lnk.amount,
                        ]
                        for lnk in flow.links
                    ]
                    csv_download(
                        f"money_flow_{flow.period_label.replace(' ', '_')}.csv",
                        ["source", "target", "amount"],
                        rows,
                    )

                export_button(_export)

            output()
            await _load()


def _node_color(kind: str) -> str:
    if kind in ("source", "deficit"):
        return CHART_INCOME
    if kind == "sink":
        return CHART_EXPENSE
    if kind == "account":
        return CHART_TEAL
    return CHART_TEAL


def _link_color(node_id: str, flow: MoneyFlow) -> str:
    kind_by_id = {n.id: n.kind for n in flow.nodes}
    kind = kind_by_id.get(node_id, "pool")
    return _node_color(kind)
