"""Largest transactions report."""

from __future__ import annotations

from typing import Any

from nicegui import ui

from kaleta.i18n import t
from kaleta.services import with_session
from kaleta.services.report_service import LargeTransaction, ReportService
from kaleta.views.components.amount_label import amount_body_cell_slot
from kaleta.views.components.empty_state import report_no_data_label
from kaleta.views.layout import page_layout
from kaleta.views.reports_canned.formatters import csv_download, fmt
from kaleta.views.reports_canned.scaffold import export_button, loading_label, report_header
from kaleta.views.theme import TABLE_SURFACE


def register() -> None:
    @ui.page("/reports/largest-transactions")
    async def page() -> None:
        state: dict[str, Any] = {"days": 90, "limit": 50, "data": None}

        with page_layout(t("reports_lib.largest_transactions")):
            report_header(
                t("reports_lib.largest_transactions"),
                t("reports_lib.largest_transactions_desc"),
            )

            async def _load() -> None:
                async def _fetch(session: Any) -> list[LargeTransaction]:
                    return await ReportService(session).largest_transactions(
                        days=int(state["days"]), limit=int(state["limit"])
                    )

                state["data"] = await with_session(_fetch)
                output.refresh()

            with ui.row().classes("items-end gap-3 mb-2"):
                ui.select(
                    {30: "30", 90: "90", 180: "180", 365: "365"},
                    label=t("reports_lib.days_back"),
                    value=state["days"],
                    on_change=lambda e: (
                        state.update(days=int(e.value)),
                        ui.timer(0.01, _load, once=True),
                    ),
                ).classes("w-32")
                ui.select(
                    {25: "25", 50: "50", 100: "100"},
                    label=t("reports_lib.limit"),
                    value=state["limit"],
                    on_change=lambda e: (
                        state.update(limit=int(e.value)),
                        ui.timer(0.01, _load, once=True),
                    ),
                ).classes("w-32")

            @ui.refreshable
            def output() -> None:
                items: list[LargeTransaction] | None = state["data"]
                if items is None:
                    loading_label()
                    return
                if not items:
                    report_no_data_label()
                    return

                cols = [
                    {"name": "date", "label": t("common.date"), "field": "date", "align": "left"},
                    {"name": "type", "label": t("common.type"), "field": "type", "align": "left"},
                    {
                        "name": "account",
                        "label": t("common.account"),
                        "field": "account",
                        "align": "left",
                    },
                    {
                        "name": "category",
                        "label": t("common.category"),
                        "field": "category",
                        "align": "left",
                    },
                    {
                        "name": "desc",
                        "label": t("common.description"),
                        "field": "desc",
                        "align": "left",
                    },
                    {
                        "name": "amount",
                        "label": t("common.amount"),
                        "field": "amount",
                        "align": "right",
                    },
                ]
                rows = [
                    {
                        "date": str(i.date),
                        "type": i.type.value,
                        "account": i.account,
                        "category": i.category,
                        "desc": i.description[:50],
                        "amount": fmt(i.amount),
                    }
                    for i in items
                ]
                tbl = ui.table(columns=cols, rows=rows).classes(TABLE_SURFACE).props("flat dense")
                tbl.add_slot("body-cell-amount", amount_body_cell_slot())

                def _export() -> None:
                    csv_download(
                        "largest_transactions.csv",
                        [
                            t("common.date"),
                            t("common.type"),
                            t("common.account"),
                            t("common.category"),
                            t("common.description"),
                            t("common.amount"),
                        ],
                        [
                            [
                                str(i.date),
                                i.type.value,
                                i.account,
                                i.category,
                                i.description,
                                i.amount,
                            ]
                            for i in items
                        ],
                    )

                export_button(_export)

            output()
            await _load()
