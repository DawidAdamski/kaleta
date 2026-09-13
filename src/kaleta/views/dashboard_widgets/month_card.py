# SPDX-License-Identifier: AGPL-3.0-or-later
"""Month card — in, out and net for the current month, plus savings pace.

Replaces the ``month_income``, ``month_expenses``, ``month_net`` and
``savings_rate_kpi`` KPI widgets (artboard ``1c``): three 26px mono figures
side by side, a ``.k-pace`` bar carrying the kept-share of income with a
tick at the target, and — below a hairline — the two slow figures that
used to be cards of their own, ``predicted_30d`` and ``net_worth``.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from nicegui import ui

from kaleta.i18n import t
from kaleta.services import ReportService
from kaleta.services.forecast_service import ForecastService
from kaleta.services.net_worth_service import NetWorthService
from kaleta.services.report_service import SavingsRatePoint
from kaleta.views.dashboard_widgets.constants import SAVINGS_RATE_TARGET_PCT
from kaleta.views.dashboard_widgets.helpers import fmt_amount
from kaleta.views.dashboard_widgets.registry import register
from kaleta.views.theme import (
    AMOUNT_EXPENSE,
    AMOUNT_INCOME,
    CARD_SUBTITLE,
    DASH_CARD,
    INK,
)


def _footer_stat(label: str, value: str) -> None:
    with ui.column().classes("gap-0 min-w-0"):
        ui.label(label).classes(CARD_SUBTITLE)
        ui.label(value).classes(f"k-mono {INK} text-[17px] font-medium")


def _figure(label: str, value: str, amount_cls: str) -> None:
    with ui.column().classes("gap-1 min-w-0 flex-1"):
        ui.label(label).classes(CARD_SUBTITLE)
        ui.label(value).classes(f"k-mono {amount_cls} text-[26px] font-medium tracking-tight")


def _pace_bar(rate: Decimal | None) -> None:
    """Savings-rate track filled to *rate*, with a tick at the target."""
    target = float(SAVINGS_RATE_TARGET_PCT)
    filled = 0.0 if rate is None else max(0.0, min(float(rate), 100.0))
    on_target = rate is not None and rate >= SAVINGS_RATE_TARGET_PCT
    fill_colour = "var(--k-income)" if on_target else "var(--k-warning)"

    with ui.row().classes("w-full items-baseline justify-between mt-5"):
        ui.label(
            t("dashboard.savings_kept_none")
            if rate is None
            else t("dashboard.savings_kept", pct=f"{float(rate):.1f}")
        ).classes(CARD_SUBTITLE)
        ui.label(t("dashboard.savings_target", pct=f"{target:.0f}")).classes(CARD_SUBTITLE)

    with ui.element("div").classes("k-pace w-full mt-2"):
        ui.element("div").classes("k-pace__fill").style(
            f"width:{filled:.2f}%;background:{fill_colour}"
        )
        ui.element("div").classes("k-pace__tick").style(f"left:{min(target, 100.0):.2f}%")


@register(
    "month_card",
    "dashboard_widgets.month_card",
    "swap_vert",
    (2, 2),
    ((2, 1), (2, 2), (4, 2)),
)
async def render_month_card(session: AsyncSession, is_dark: bool) -> None:  # noqa: ARG001
    income, expenses = await ReportService(session).current_month_summary()
    net = income - expenses
    today = datetime.date.today()
    # The service owns the formula; the card only asks this month's point for it.
    rate = SavingsRatePoint(today.year, today.month, income, expenses).rate_pct
    summary = await NetWorthService(session).get_summary(history_months=2)
    forecast = await ForecastService(session).forecast_account(account_id=None, horizon_days=30)
    predicted = forecast.predicted_balance_30d

    with ui.card().classes(f"{DASH_CARD} justify-between"):
        with ui.column().classes("gap-1 w-full"):
            ui.label(t("dashboard_widgets.month_card")).classes("k-eyebrow")
            with ui.row().classes("w-full gap-6 mt-2 no-wrap"):
                _figure(t("common.income"), fmt_amount(income).removesuffix(" zł"), AMOUNT_INCOME)
                _figure(
                    t("common.expense"), fmt_amount(expenses).removesuffix(" zł"), AMOUNT_EXPENSE
                )
                _figure(t("dashboard.net"), fmt_amount(net).removesuffix(" zł"), INK)

        _pace_bar(rate)

        with ui.row().classes("w-full gap-6 pt-4 mt-4 k-card-footer flex-wrap"):
            _footer_stat(
                t("dashboard.balance_30"),
                "—" if predicted is None else fmt_amount(predicted).removesuffix(" zł"),
            )
            _footer_stat(
                t("dashboard_widgets.net_worth"),
                fmt_amount(summary.net_worth).removesuffix(" zł"),
            )
