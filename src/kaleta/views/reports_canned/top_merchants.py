"""Top merchants report."""

from __future__ import annotations

import datetime
from typing import Any

from nicegui import app, ui

from kaleta.i18n import t
from kaleta.services import with_session
from kaleta.services.report_service import MerchantSpend, ReportService
from kaleta.views.chart_utils import apply_dark
from kaleta.views.components.empty_state import report_no_data_label
from kaleta.views.layout import page_layout
from kaleta.views.reports_canned.formatters import csv_download, fmt
from kaleta.views.reports_canned.scaffold import (
    date_range_controls,
    export_button,
    loading_label,
    report_header,
)
from kaleta.views.theme import SECTION_CARD, SECTION_TITLE, TABLE_SURFACE


def register() -> None:
    @ui.page("/reports/top-merchants")
    async def page() -> None:
        is_dark: bool = app.storage.user.get("dark_mode", False)
        today = datetime.date.today()
        state: dict[str, Any] = {
            "start": (today - datetime.timedelta(days=30)).isoformat(),
            "end": today.isoformat(),
            "data": None,
        }

        with page_layout(t("reports_lib.top_merchants")):
            report_header(t("reports_lib.top_merchants"), t("reports_lib.top_merchants_desc"))

            async def _load() -> None:
                async def _fetch(session: Any) -> list[MerchantSpend]:
                    return await ReportService(session).top_merchants(
                        datetime.date.fromisoformat(state["start"]),
                        datetime.date.fromisoformat(state["end"]) + datetime.timedelta(days=1),
                        limit=20,
                    )

                state["data"] = await with_session(_fetch)
                output.refresh()

            date_range_controls(state, lambda: ui.timer(0.01, _load, once=True))

            @ui.refreshable
            def output() -> None:
                merchants: list[MerchantSpend] | None = state["data"]
                if merchants is None:
                    loading_label()
                    return
                if not merchants:
                    report_no_data_label()
                    return

                with ui.card().classes(SECTION_CARD):
                    ui.label(t("reports_lib.top_merchants")).classes(SECTION_TITLE)
                    sorted_asc = list(reversed(merchants))
                    ui.echart(
                        apply_dark(
                            {
                                "tooltip": {"trigger": "axis"},
                                "grid": {
                                    "left": "3%",
                                    "right": "4%",
                                    "bottom": "8%",
                                    "containLabel": True,
                                },
                                "xAxis": {"type": "value"},
                                "yAxis": {
                                    "type": "category",
                                    "data": [m.name for m in sorted_asc],
                                },
                                "series": [
                                    {
                                        "name": t("common.amount"),
                                        "type": "bar",
                                        "data": [float(m.amount) for m in sorted_asc],
                                        "itemStyle": {"color": "#009688"},
                                        "label": {
                                            "show": True,
                                            "position": "right",
                                            "formatter": "{c}",
                                        },
                                    }
                                ],
                            },
                            is_dark,
                        )
                    ).classes("w-full").style(f"height: {max(300, 30 * len(merchants))}px")

                cols = [
                    {"name": "name", "label": t("common.payee"), "field": "name", "align": "left"},
                    {
                        "name": "amount",
                        "label": t("common.amount"),
                        "field": "amount",
                        "align": "right",
                    },
                    {
                        "name": "count",
                        "label": t("reports_lib.transaction_count"),
                        "field": "count",
                        "align": "right",
                    },
                ]
                rows = [
                    {"name": m.name, "amount": fmt(m.amount), "count": m.count} for m in merchants
                ]
                ui.table(columns=cols, rows=rows).classes(TABLE_SURFACE).props("flat dense")

                def _export() -> None:
                    csv_download(
                        "top_merchants.csv",
                        [t("common.payee"), t("common.amount"), t("reports_lib.transaction_count")],
                        [[m.name, m.amount, m.count] for m in merchants],
                    )

                export_button(_export)

            output()
            await _load()
