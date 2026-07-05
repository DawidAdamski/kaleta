# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cash flow statement report."""

from __future__ import annotations

import datetime
from typing import Any

from nicegui import app, ui

from kaleta.i18n import t
from kaleta.services import with_session
from kaleta.services.report_service import CashFlowStatement, ReportService
from kaleta.views.chart_utils import apply_dark
from kaleta.views.layout import page_layout
from kaleta.views.reports_canned.formatters import csv_download, fmt
from kaleta.views.reports_canned.scaffold import (
    export_button,
    kpi,
    loading_label,
    month_controls,
    report_header,
)
from kaleta.views.theme import SECTION_CARD, SECTION_TITLE


def register() -> None:
    @ui.page("/reports/cash-flow")
    async def page() -> None:
        is_dark: bool = app.storage.user.get("dark_mode", False)
        today = datetime.date.today()
        state: dict[str, Any] = {"year": today.year, "month": today.month, "data": None}

        with page_layout(t("reports_lib.cash_flow")):
            report_header(t("reports_lib.cash_flow"), t("reports_lib.cash_flow_desc"))

            async def _load() -> None:
                async def _fetch(session: Any) -> CashFlowStatement:
                    return await ReportService(session).cash_flow_statement(
                        state["year"], state["month"]
                    )

                state["data"] = await with_session(_fetch)
                output.refresh()

            month_controls(state, lambda: ui.timer(0.01, _load, once=True))

            @ui.refreshable
            def output() -> None:
                cfs: CashFlowStatement | None = state["data"]
                if cfs is None:
                    loading_label()
                    return

                with ui.row().classes("w-full gap-3 flex-wrap mb-3"):
                    kpi(t("reports_lib.inflows"), fmt(cfs.total_inflows), "south_west", "green-7")
                    kpi(t("reports_lib.outflows"), fmt(cfs.total_outflows), "north_east", "red-7")
                    kpi(
                        t("reports_lib.net_cash_flow"),
                        fmt(cfs.net_cash_flow),
                        "sync_alt",
                        "green-7" if cfs.net_cash_flow >= 0 else "red-7",
                    )

                with ui.card().classes(SECTION_CARD):
                    ui.label(t("reports_lib.flows_by_category")).classes(SECTION_TITLE)
                    in_labels = [r.category for r in cfs.inflows]
                    in_vals = [float(r.amount) for r in cfs.inflows]
                    out_labels = [r.category for r in cfs.outflows]
                    out_vals = [-float(r.amount) for r in cfs.outflows]
                    ui.echart(
                        apply_dark(
                            {
                                "tooltip": {"trigger": "axis"},
                                "grid": {
                                    "left": "3%",
                                    "right": "4%",
                                    "bottom": "12%",
                                    "containLabel": True,
                                },
                                "xAxis": {"type": "value"},
                                "yAxis": {"type": "category", "data": in_labels + out_labels},
                                "series": [
                                    {
                                        "name": t("reports_lib.inflows"),
                                        "type": "bar",
                                        "data": in_vals + [0] * len(out_labels),
                                        "itemStyle": {"color": "#4caf50"},
                                    },
                                    {
                                        "name": t("reports_lib.outflows"),
                                        "type": "bar",
                                        "data": [0] * len(in_labels) + out_vals,
                                        "itemStyle": {"color": "#ef5350"},
                                    },
                                ],
                            },
                            is_dark,
                        )
                    ).classes("w-full").style("height: 400px")

                def _export() -> None:
                    rows: list[list[Any]] = []
                    for r in cfs.inflows:
                        rows.append(["inflow", r.category, r.amount])
                    for r in cfs.outflows:
                        rows.append(["outflow", r.category, r.amount])
                    csv_download(
                        f"cash_flow_{cfs.year}_{cfs.month:02d}.csv",
                        [t("common.type"), t("common.category"), t("common.amount")],
                        rows,
                    )

                export_button(_export)

            output()
            await _load()
