"""Dashboard Command Center — widget catalog.

Each widget is a small, self-contained async function that reads its own
data slice (via the services layer) and renders a card. Widgets are grouped
by `size` so the dashboard can lay them out coherently:

* ``kpi``   — narrow card, rendered in a single `flex-wrap` row at the top.
* ``half``  — half-width card, rendered in a responsive 2-column grid.
* ``full``  — full-width card, stacked below.

Users pick which widgets they want and in what order via the Customize
dialog; the selection is persisted in ``app.storage.user["dashboard_widgets"]``.
"""

from __future__ import annotations

import datetime
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from nicegui import ui
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.i18n import t
from kaleta.models.transaction import TransactionType
from kaleta.services import ReportService
from kaleta.services.forecast_service import ForecastService
from kaleta.services.net_worth_service import NetWorthService
from kaleta.services.planned_transaction_service import PlannedTransactionService
from kaleta.services.report_service import MonthCashflow
from kaleta.views.chart_utils import apply_dark
from kaleta.views.theme import (
    AMOUNT_EXPENSE,
    AMOUNT_INCOME,
    AMOUNT_NEUTRAL,
    BODY_MUTED,
    SECTION_CARD,
    SECTION_HEADING,
    SECTION_TITLE,
    TABLE_SURFACE,
    kpi_card_classes,
)

WidgetSize = Literal["kpi", "half", "full"]

RenderFn = Callable[[AsyncSession, bool], Awaitable[None]]


@dataclass(frozen=True)
class Widget:
    id: str
    title_key: str
    icon: str
    size: WidgetSize
    render: RenderFn


WIDGETS: dict[str, Widget] = {}


def _register(
    widget_id: str,
    title_key: str,
    icon: str,
    size: WidgetSize,
) -> Callable[[RenderFn], RenderFn]:
    def wrap(fn: RenderFn) -> RenderFn:
        WIDGETS[widget_id] = Widget(
            id=widget_id, title_key=title_key, icon=icon, size=size, render=fn
        )
        return fn
    return wrap


# ── Shared helpers ────────────────────────────────────────────────────────────


def _fmt(amount: Decimal | float | int) -> str:
    return f"{float(amount):,.2f} zł"


def _kpi_card(
    title: str, value: str, icon: str, icon_color: str, extra_cls: str = ""
) -> None:
    with ui.card().classes(kpi_card_classes()), ui.row().classes(
        "items-center gap-4 w-full"
    ):
        with ui.element("div").classes(
            f"h-11 w-11 rounded-2xl bg-{icon_color.split('-')[0]}-500/10 "
            f"text-{icon_color.split('-')[0]}-600 flex items-center justify-center"
        ):
            ui.icon(icon, size="1.8rem")
        with ui.column().classes("gap-0"):
            ui.label(title).classes(SECTION_TITLE)
            ui.label(value).classes(
                f"text-2xl font-semibold tracking-tight {extra_cls}"
            )


def _section_card(title: str, *, subtitle: str | None = None) -> Any:
    card = ui.card().classes(SECTION_CARD)
    with card:
        ui.label(title).classes(SECTION_TITLE)
        if subtitle:
            ui.label(subtitle).classes(f"{SECTION_HEADING} mb-3")
    return card


# ── KPI widgets ───────────────────────────────────────────────────────────────


@_register("total_balance", "dashboard_widgets.total_balance", "account_balance", "kpi")
async def _total_balance(session: AsyncSession, is_dark: bool) -> None:
    total = await ReportService(session).total_balance()
    _kpi_card(t("dashboard.total_balance"), _fmt(total), "account_balance", "blue-7")


@_register("month_income", "dashboard_widgets.month_income", "trending_up", "kpi")
async def _month_income(session: AsyncSession, is_dark: bool) -> None:
    income, _ = await ReportService(session).current_month_summary()
    _kpi_card(t("dashboard.month_income"), _fmt(income), "trending_up", "green-7")


@_register("month_expenses", "dashboard_widgets.month_expenses", "trending_down", "kpi")
async def _month_expenses(session: AsyncSession, is_dark: bool) -> None:
    _, expenses = await ReportService(session).current_month_summary()
    _kpi_card(
        t("dashboard.month_expenses"), _fmt(expenses), "trending_down", "red-7"
    )


@_register("month_net", "dashboard_widgets.month_net", "swap_vert", "kpi")
async def _month_net(session: AsyncSession, is_dark: bool) -> None:
    income, expenses = await ReportService(session).current_month_summary()
    net = income - expenses
    color_cls = "text-green-700" if net >= 0 else "text-red-700"
    _kpi_card(
        t("dashboard.month_net"), _fmt(net), "swap_vert", "orange-7", extra_cls=color_cls
    )


@_register("predicted_30d", "dashboard_widgets.predicted_30d", "insights", "kpi")
async def _predicted_30d(session: AsyncSession, is_dark: bool) -> None:
    total = await ReportService(session).total_balance()
    result = await ForecastService(session).forecast_account(
        account_id=None, horizon_days=30
    )
    pred = result.predicted_balance_30d
    if pred is None:
        _kpi_card(t("dashboard.balance_30"), "—", "insights", "grey-6")
        return
    color = "green-7" if pred >= float(total) else "red-7"
    _kpi_card(t("dashboard.balance_30"), _fmt(pred), "insights", color)


@_register("net_worth", "dashboard_widgets.net_worth", "account_balance_wallet", "kpi")
async def _net_worth(session: AsyncSession, is_dark: bool) -> None:
    summary = await NetWorthService(session).get_summary(history_months=2)
    _kpi_card(
        t("dashboard_widgets.net_worth"),
        _fmt(summary.net_worth),
        "account_balance_wallet",
        "deep-purple-7",
    )


@_register("savings_rate_kpi", "dashboard_widgets.savings_rate_kpi", "savings", "kpi")
async def _savings_rate_kpi(session: AsyncSession, is_dark: bool) -> None:
    points = await ReportService(session).savings_rate(months=1)
    latest = points[0] if points else None
    rate = latest.rate_pct if latest else None
    value = "—" if rate is None else f"{float(rate):.1f}%"
    color = "green-7" if rate is not None and rate >= 20 else "orange-7"
    _kpi_card(t("dashboard_widgets.savings_rate_kpi"), value, "savings", color)


# ── Half-width widgets ────────────────────────────────────────────────────────


@_register("cashflow_chart", "dashboard_widgets.cashflow_chart", "bar_chart", "full")
async def _cashflow_chart(session: AsyncSession, is_dark: bool) -> None:
    months = await ReportService(session).cashflow_last_n_months(6)
    with _section_card(
        t("dashboard.cashflow_chart"), subtitle=t("dashboard_widgets.cashflow_sub")
    ):
        ui.echart(_build_cashflow_chart(months, is_dark)).classes("w-full h-72")


def _build_cashflow_chart(
    months: list[MonthCashflow], is_dark: bool
) -> dict[str, Any]:
    opts: dict[str, Any] = {
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "legend": {
            "data": [t("common.income"), t("common.expense"), t("dashboard.net")],
            "bottom": 0,
        },
        "grid": {"left": "3%", "right": "4%", "bottom": "12%", "containLabel": True},
        "xAxis": {"type": "category", "data": [m.label for m in months]},
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
    return apply_dark(opts, is_dark)


@_register(
    "savings_rate_trend",
    "dashboard_widgets.savings_rate_trend",
    "show_chart",
    "half",
)
async def _savings_rate_trend(session: AsyncSession, is_dark: bool) -> None:
    points = await ReportService(session).savings_rate(months=6)
    labels = [p.label for p in points]
    rates = [float(p.rate_pct) if p.rate_pct is not None else None for p in points]
    opts: dict[str, Any] = {
        "tooltip": {"trigger": "axis"},
        "grid": {"left": "3%", "right": "4%", "bottom": "8%", "containLabel": True},
        "xAxis": {"type": "category", "data": labels},
        "yAxis": {"type": "value", "axisLabel": {"formatter": "{value}%"}},
        "series": [
            {
                "name": t("dashboard_widgets.savings_rate_trend"),
                "type": "line",
                "data": rates,
                "smooth": True,
                "itemStyle": {"color": "#26a69a"},
                "areaStyle": {"color": "#26a69a", "opacity": 0.15},
            }
        ],
    }
    with _section_card(
        t("dashboard_widgets.savings_rate_trend"),
        subtitle=t("dashboard_widgets.savings_rate_sub"),
    ):
        ui.echart(apply_dark(opts, is_dark)).classes("w-full h-56")


@_register(
    "budget_variance_month",
    "dashboard_widgets.budget_variance_month",
    "rule",
    "half",
)
async def _budget_variance_month(session: AsyncSession, is_dark: bool) -> None:
    today = datetime.date.today()
    rep = await ReportService(session).budget_variance(today.year, today.month)
    with _section_card(
        t("dashboard_widgets.budget_variance_month"),
        subtitle=t("dashboard_widgets.budget_variance_sub"),
    ):
        if not rep.rows:
            ui.label(t("dashboard_widgets.no_budgets")).classes(BODY_MUTED)
            return
        over = rep.over_budget_rows[:5]
        if not over:
            ui.label(t("dashboard_widgets.all_on_track")).classes(
                "text-positive text-sm font-medium"
            )
        with ui.column().classes("w-full gap-2 mt-1"):
            for row in over:
                pct = row.variance_pct
                pct_txt = "—" if pct is None else f"{float(pct):.0f}%"
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label(row.category).classes("text-sm")
                    ui.label(
                        f"{_fmt(row.actual)} / {_fmt(row.planned)} ({pct_txt})"
                    ).classes("text-sm text-red-600 font-medium")


@_register("top_merchants", "dashboard_widgets.top_merchants", "store", "half")
async def _top_merchants(session: AsyncSession, is_dark: bool) -> None:
    today = datetime.date.today()
    start = today - datetime.timedelta(days=30)
    merchants = await ReportService(session).top_merchants(start, today, limit=5)
    with _section_card(
        t("dashboard_widgets.top_merchants"),
        subtitle=t("dashboard_widgets.top_merchants_sub"),
    ):
        if not merchants:
            ui.label(t("dashboard_widgets.no_merchants")).classes(BODY_MUTED)
            return
        with ui.column().classes("w-full gap-1 mt-1"):
            for m in merchants:
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label(m.name).classes("text-sm truncate")
                    ui.label(_fmt(m.amount)).classes("text-sm font-medium")


@_register("ytd_summary", "dashboard_widgets.ytd_summary", "calendar_today", "half")
async def _ytd_summary(session: AsyncSession, is_dark: bool) -> None:
    rep = await ReportService(session).ytd_summary()
    with _section_card(
        t("dashboard_widgets.ytd_summary"),
        subtitle=t("dashboard_widgets.ytd_summary_sub"),
    ), ui.row().classes("w-full gap-4 flex-wrap mt-1"):
        _mini_stat(t("reports_lib.ytd_income"), _fmt(rep.income), "green-7")
        _mini_stat(t("reports_lib.ytd_expenses"), _fmt(rep.expenses), "red-7")
        _mini_stat(t("reports_lib.ytd_net"), _fmt(rep.net), "blue-7")
        rate = rep.savings_rate_pct
        rate_txt = "—" if rate is None else f"{float(rate):.1f}%"
        _mini_stat(t("reports_lib.savings_rate"), rate_txt, "purple-7")


def _mini_stat(label: str, value: str, color: str) -> None:
    with ui.column().classes("gap-0 min-w-28"):
        ui.label(label).classes("text-xs text-grey-6 uppercase tracking-wide")
        ui.label(value).classes(f"text-lg font-semibold text-{color}")


@_register(
    "upcoming_planned",
    "dashboard_widgets.upcoming_planned",
    "event_upcoming",
    "half",
)
async def _upcoming_planned(session: AsyncSession, is_dark: bool) -> None:
    today = datetime.date.today()
    horizon = today + datetime.timedelta(days=14)
    occs = await PlannedTransactionService(session).get_occurrences(
        today, horizon, account_id=None, active_only=True
    )
    with _section_card(
        t("dashboard_widgets.upcoming_planned"),
        subtitle=t("dashboard_widgets.upcoming_planned_sub"),
    ):
        if not occs:
            ui.label(t("dashboard_widgets.nothing_planned")).classes(BODY_MUTED)
            return
        with ui.column().classes("w-full gap-1 mt-1"):
            for occ in occs[:6]:
                is_income = occ.type == TransactionType.INCOME
                amount_cls = "text-positive" if is_income else "text-negative"
                sign = "+" if is_income else "-"
                with ui.row().classes("w-full items-center justify-between"):
                    with ui.column().classes("gap-0"):
                        ui.label(occ.name).classes("text-sm")
                        ui.label(str(occ.date)).classes("text-xs text-grey-6")
                    ui.label(f"{sign}{_fmt(occ.amount).lstrip('-')}").classes(
                        f"text-sm font-medium {amount_cls}"
                    )


@_register(
    "largest_transactions",
    "dashboard_widgets.largest_transactions",
    "format_list_numbered",
    "half",
)
async def _largest_transactions(session: AsyncSession, is_dark: bool) -> None:
    rows = await ReportService(session).largest_transactions(
        days=30, limit=5, tx_type=TransactionType.EXPENSE
    )
    with _section_card(
        t("dashboard_widgets.largest_transactions"),
        subtitle=t("dashboard_widgets.largest_transactions_sub"),
    ):
        if not rows:
            ui.label(t("dashboard_widgets.no_transactions")).classes(BODY_MUTED)
            return
        with ui.column().classes("w-full gap-1 mt-1"):
            for r in rows:
                with ui.row().classes("w-full items-center justify-between"):
                    with ui.column().classes("gap-0"):
                        ui.label(r.description or r.category).classes(
                            "text-sm truncate"
                        )
                        ui.label(f"{r.date} · {r.category}").classes(
                            "text-xs text-grey-6"
                        )
                    ui.label(_fmt(r.amount)).classes(
                        f"text-sm font-medium {AMOUNT_EXPENSE}"
                    )


# ── Full-width widgets ────────────────────────────────────────────────────────


@_register("quick_actions", "dashboard_widgets.quick_actions", "bolt", "full")
async def _quick_actions(session: AsyncSession, is_dark: bool) -> None:
    with _section_card(
        t("dashboard_widgets.quick_actions"),
        subtitle=t("dashboard_widgets.quick_actions_sub"),
    ), ui.row().classes("w-full gap-2 flex-wrap"):
        _quick_btn("add", t("dashboard_widgets.qa_add_tx"), "/transactions")
        _quick_btn(
            "insights", t("dashboard_widgets.qa_forecast"), "/forecast"
        )
        _quick_btn("assessment", t("dashboard_widgets.qa_reports"), "/reports")
        _quick_btn(
            "account_balance_wallet",
            t("dashboard_widgets.qa_net_worth"),
            "/net-worth",
        )
        _quick_btn("rule", t("dashboard_widgets.qa_budgets"), "/budgets")
        _quick_btn("upload_file", t("dashboard_widgets.qa_import"), "/import")


def _quick_btn(icon: str, label: str, route: str) -> None:
    ui.button(label, icon=icon, on_click=lambda r=route: ui.navigate.to(r)).props(
        "flat color=primary"
    ).classes("flex-1 min-w-40")


@_register(
    "recent_transactions",
    "dashboard_widgets.recent_transactions",
    "receipt_long",
    "full",
)
async def _recent_transactions(session: AsyncSession, is_dark: bool) -> None:
    recent = await ReportService(session).recent_transactions(10)
    with ui.card().classes(SECTION_CARD):
        with ui.row().classes("w-full items-center justify-between mb-3"):
            with ui.column().classes("gap-1"):
                ui.label(t("dashboard.recent_transactions")).classes(SECTION_TITLE)
                ui.label(t("dashboard_widgets.recent_transactions_sub")).classes(
                    SECTION_HEADING
                )
            ui.button(
                t("dashboard.view_all"),
                icon="arrow_forward",
                on_click=lambda: ui.navigate.to("/transactions"),
            ).props("flat dense")

        if not recent:
            ui.label(t("dashboard.no_transactions")).classes(BODY_MUTED)
            return

        columns = [
            {"name": "date", "label": t("common.date"), "field": "date", "align": "left"},
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
                "type": tx.type.value,
                "amount": (
                    f"+{tx.amount:,.2f}"
                    if tx.type == TransactionType.INCOME
                    else f"-{tx.amount:,.2f}"
                ),
            }
            for tx in recent
        ]
        tbl = ui.table(columns=columns, rows=rows).classes(TABLE_SURFACE).props(
            "dense flat"
        )
        tbl.add_slot(
            "body-cell-amount",
            '<q-td :props="props" class="text-right">'
            f"<span :class=\"props.row.type === 'income' ? '{AMOUNT_INCOME}' : "
            f"props.row.type === 'expense' ? '{AMOUNT_EXPENSE}' "
            f": '{AMOUNT_NEUTRAL}'\">"
            "{{ props.row.amount }}</span></q-td>",
        )


@_register(
    "net_worth_trend",
    "dashboard_widgets.net_worth_trend",
    "trending_up",
    "full",
)
async def _net_worth_trend(session: AsyncSession, is_dark: bool) -> None:
    summary = await NetWorthService(session).get_summary(history_months=12)
    history = summary.history
    with _section_card(
        t("dashboard_widgets.net_worth_trend"),
        subtitle=t("dashboard_widgets.net_worth_trend_sub"),
    ):
        if not history:
            ui.label(t("dashboard_widgets.no_history")).classes(BODY_MUTED)
            return
        labels = [f"{h.year}-{h.month:02d}" for h in history]
        net_values = [float(h.net_worth) for h in history]
        opts: dict[str, Any] = {
            "tooltip": {"trigger": "axis"},
            "grid": {
                "left": "3%",
                "right": "4%",
                "bottom": "8%",
                "containLabel": True,
            },
            "xAxis": {"type": "category", "data": labels},
            "yAxis": {"type": "value", "axisLabel": {"formatter": "{value} zł"}},
            "series": [
                {
                    "name": t("dashboard_widgets.net_worth"),
                    "type": "line",
                    "data": net_values,
                    "smooth": True,
                    "areaStyle": {"color": "#7e57c2", "opacity": 0.18},
                    "itemStyle": {"color": "#7e57c2"},
                    "lineStyle": {"width": 2},
                    "symbol": "circle",
                    "symbolSize": 5,
                }
            ],
        }
        ui.echart(apply_dark(opts, is_dark)).classes("w-full h-64")


# ── Default layout ────────────────────────────────────────────────────────────


DEFAULT_WIDGETS: list[str] = [
    "total_balance",
    "month_income",
    "month_expenses",
    "month_net",
    "predicted_30d",
    "net_worth",
    "savings_rate_kpi",
    "cashflow_chart",
    "budget_variance_month",
    "top_merchants",
    "ytd_summary",
    "upcoming_planned",
    "largest_transactions",
    "savings_rate_trend",
    "quick_actions",
    "recent_transactions",
    "net_worth_trend",
]


def resolve_user_widgets(stored: Any) -> list[str]:
    """Validate user-stored widget order, fall back to defaults when missing."""
    if not isinstance(stored, list) or not stored:
        return list(DEFAULT_WIDGETS)
    cleaned = [w for w in stored if isinstance(w, str) and w in WIDGETS]
    return cleaned or list(DEFAULT_WIDGETS)
