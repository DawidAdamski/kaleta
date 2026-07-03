"""Net worth statement — summary with link to full net-worth page."""

from __future__ import annotations

from typing import Any

from nicegui import app, ui

from kaleta.i18n import t
from kaleta.services import with_session
from kaleta.services.net_worth_service import NetWorthService
from kaleta.views.layout import page_layout
from kaleta.views.reports_canned.formatters import csv_download, fmt
from kaleta.views.reports_canned.scaffold import export_button, kpi, report_header
from kaleta.views.theme import TABLE_SURFACE


def register() -> None:
    @ui.page("/reports/net-worth-statement")
    async def page() -> None:
        default_currency: str = app.storage.user.get("currency", "PLN")

        async def _fetch(session: Any) -> Any:
            return await NetWorthService(session).get_summary(
                history_months=13, default_currency=default_currency
            )

        summary = await with_session(_fetch)

        with page_layout(t("reports_lib.net_worth_statement")):
            report_header(
                t("reports_lib.net_worth_statement"),
                t("reports_lib.net_worth_statement_desc"),
            )

            with ui.row().classes("w-full gap-3 flex-wrap mb-3"):
                kpi(
                    t("net_worth.total_assets"),
                    fmt(summary.total_assets),
                    "trending_up",
                    "green-7",
                )
                kpi(
                    t("net_worth.total_liabilities"),
                    fmt(summary.total_liabilities),
                    "trending_down",
                    "red-7",
                )
                kpi(
                    t("net_worth.net_worth"),
                    fmt(summary.net_worth),
                    "account_balance",
                    "green-7" if summary.net_worth >= 0 else "red-7",
                )

            cols = [
                {"name": "name", "label": t("common.account"), "field": "name", "align": "left"},
                {"name": "kind", "label": t("common.type"), "field": "kind", "align": "left"},
                {
                    "name": "balance",
                    "label": t("common.balance"),
                    "field": "balance",
                    "align": "right",
                },
            ]
            rows = [
                {
                    "name": a.name,
                    "kind": t("reports_lib.asset") if a.is_asset else t("reports_lib.liability"),
                    "balance": fmt(a.balance_in_default),
                }
                for a in summary.accounts
            ]
            ui.table(columns=cols, rows=rows).classes(TABLE_SURFACE).props("flat dense")

            ui.button(
                t("net_worth.title"),
                icon="open_in_new",
                on_click=lambda: ui.navigate.to("/net-worth"),
            ).props("flat color=primary")

            def _export() -> None:
                csv_download(
                    "net_worth_statement.csv",
                    [t("common.account"), t("common.type"), t("common.balance")],
                    [
                        [
                            a.name,
                            "asset" if a.is_asset else "liability",
                            a.balance_in_default,
                        ]
                        for a in summary.accounts
                    ],
                )

            export_button(_export)
