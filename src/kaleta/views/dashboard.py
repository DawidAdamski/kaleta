from __future__ import annotations

from decimal import Decimal
from typing import Any

from nicegui import app, ui

from kaleta.db import AsyncSessionFactory
from kaleta.i18n import t
from kaleta.models.transaction import TransactionType
from kaleta.services import ReportService
from kaleta.services.forecast_service import ForecastService
from kaleta.services.report_service import MonthCashflow
from kaleta.views.chart_utils import apply_dark
from kaleta.views.layout import page_layout


def _fmt(amount: Decimal) -> str:
    return f"{amount:,.2f} zł"


def _cashflow_chart_options(months: list[MonthCashflow], is_dark: bool = False) -> dict[str, Any]:
    _opts = {
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "legend": {
            "data": [t("common.income"), t("common.expense"), t("dashboard.net")],
            "bottom": 0,
        },
        "grid": {"left": "3%", "right": "4%", "bottom": "12%", "containLabel": True},
        "xAxis": {
            "type": "category",
            "data": [m.label for m in months],
        },
        "yAxis": {"type": "value", "axisLabel": {"formatter": "{value} zł"}},
        "series": [
            {
                "name": t("common.income"),
                "type": "bar",
                "stack": "cashflow",
                "data": [float(m.income) for m in months],
                "itemStyle": {"color": "#4caf50"},
            },
            {
                "name": t("common.expense"),
                "type": "bar",
                "stack": "cashflow",
                "data": [-float(m.expenses) for m in months],
                "itemStyle": {"color": "#ef5350"},
            },
            {
                "name": t("dashboard.net"),
                "type": "line",
                "data": [float(m.net) for m in months],
                "itemStyle": {"color": "#1976d2"},
                "lineStyle": {"width": 2},
                "symbol": "circle",
                "symbolSize": 6,
            },
        ],
    }
    return apply_dark(_opts, is_dark)


def register() -> None:
    @ui.page("/")
    async def dashboard() -> None:
        is_dark: bool = app.storage.user.get("dark_mode", False)
        async with AsyncSessionFactory() as session:
            svc = ReportService(session)
            total_balance = await svc.total_balance()
            income, expenses = await svc.current_month_summary()
            cashflow = await svc.cashflow_last_n_months(6)
            recent = await svc.recent_transactions(10)
            forecast_result = await ForecastService(session).forecast_account(
                account_id=None, horizon_days=30
            )

        net = income - expenses
        net_color = "text-green-700" if net >= 0 else "text-red-700"
        pred_30 = forecast_result.predicted_balance_30d

        with page_layout(t("dashboard.title")):
            ui.label(t("dashboard.title")).classes("text-2xl font-bold")

            # ── KPI cards ────────────────────────────────────────────────────
            with ui.row().classes("w-full gap-4 flex-wrap"):
                _kpi(t("dashboard.total_balance"), _fmt(total_balance), "account_balance", "blue-7")
                _kpi(t("dashboard.month_income"), _fmt(income), "trending_up", "green-7")
                _kpi(t("dashboard.month_expenses"), _fmt(expenses), "trending_down", "red-7")
                _kpi(
                    t("dashboard.month_net"),
                    _fmt(net),
                    "swap_vert",
                    "orange-7",
                    extra_cls=net_color,
                )
                if pred_30 is not None:
                    pred_color = "green-7" if pred_30 >= float(total_balance) else "red-7"
                    _kpi(
                        t("dashboard.balance_30"),
                        f"{pred_30:,.2f} zł",
                        "insights",
                        pred_color,
                    )

            # ── Cashflow chart ───────────────────────────────────────────────
            with ui.card().classes("w-full"):
                ui.label(t("dashboard.cashflow_chart")).classes("text-lg font-semibold mb-2")
                ui.echart(_cashflow_chart_options(cashflow, is_dark)).classes("w-full h-72")

            # ── Recent transactions ──────────────────────────────────────────
            with ui.card().classes("w-full"):
                with ui.row().classes("w-full items-center justify-between mb-2"):
                    ui.label(t("dashboard.recent_transactions")).classes("text-lg font-semibold")
                    ui.button(
                        t("dashboard.view_all"),
                        on_click=lambda: ui.navigate.to("/transactions"),
                    ).props("flat dense")

                if not recent:
                    ui.label(t("dashboard.no_transactions")).classes("text-grey-6")
                else:
                    columns = [
                        {
                            "name": "date",
                            "label": t("common.date"),
                            "field": "date",
                            "align": "left",
                        },
                        {
                            "name": "account",
                            "label": t("common.account"),
                            "field": "account",
                            "align": "left",
                        },
                        {
                            "name": "desc",
                            "label": t("common.description"),
                            "field": "desc",
                            "align": "left",
                        },
                        {
                            "name": "category",
                            "label": t("common.category"),
                            "field": "category",
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
                            "date": str(tx.date),
                            "account": tx.account.name if tx.account else "—",
                            "desc": (tx.description or "—")[:45],
                            "category": tx.category.name if tx.category else "—",
                            "amount": (
                                f"+{tx.amount:,.2f}"
                                if tx.type == TransactionType.INCOME
                                else f"-{tx.amount:,.2f}"
                            ),
                        }
                        for tx in recent
                    ]
                    ui.table(columns=columns, rows=rows).classes("w-full").props("dense flat")


def _kpi(title: str, value: str, icon: str, icon_color: str, extra_cls: str = "") -> None:
    with ui.card().classes("flex-1 min-w-44"), ui.row().classes("items-center gap-3 w-full"):
        ui.icon(icon, size="2.2rem").classes(f"text-{icon_color}")
        with ui.column().classes("gap-0"):
            ui.label(title).classes("text-xs text-grey-6 uppercase tracking-wide")
            ui.label(value).classes(f"text-xl font-bold {extra_cls}")
