# SPDX-License-Identifier: AGPL-3.0-or-later
"""Balance card — the dashboard's hero figure plus its per-account breakdown.

Replaces the ``total_balance`` KPI widget (artboard ``1c``): one 54px mono
figure with muted decimals, the delta since the reference date, and the
accounts that make it up as quiet tiles underneath. Net worth and the
30-day prediction live in the month card's footer, where ``1c`` puts them.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from nicegui import ui

from kaleta.i18n import t
from kaleta.services import AccountService, ReportService
from kaleta.views.dashboard_widgets.helpers import (
    fmt_amount,
    format_kpi_trend,
    hero_figure,
    trend_class,
)
from kaleta.views.dashboard_widgets.registry import register
from kaleta.views.theme import CARD_SUBTITLE, DASH_CARD, INK

#: Accounts shown as chips under the hero before the list is truncated.
_MAX_ACCOUNT_CHIPS = 3


def _account_chip(name: str, balance: Decimal) -> None:
    with ui.column().classes("k-account-chip gap-0.5 rounded-lg px-3.5 py-3 flex-1 min-w-32"):
        ui.label(name).classes(f"{CARD_SUBTITLE} truncate")
        ui.label(fmt_amount(balance).removesuffix(" zł")).classes(
            f"k-mono {INK} text-[16px] font-medium"
        )


@register(
    "balance_card",
    "dashboard_widgets.balance_card",
    "account_balance",
    (2, 2),
    ((2, 2), (4, 2)),
)
async def render_balance_card(session: AsyncSession, is_dark: bool) -> None:  # noqa: ARG001
    reports = ReportService(session)
    total = await reports.total_balance()
    delta = await reports.balance_delta_vs_days_ago(30)
    accounts = await AccountService(session).list()

    with ui.card().classes(f"{DASH_CARD} justify-between"):
        with ui.column().classes("gap-1 w-full"):
            ui.label(t("dashboard.total_balance")).classes("k-eyebrow")
            hero_figure(total)
            ui.label(format_kpi_trend(delta)).classes(f"text-xs {trend_class(delta)}")

        with ui.row().classes("w-full gap-2.5 flex-wrap mt-5"):
            for account in accounts[:_MAX_ACCOUNT_CHIPS]:
                _account_chip(account.name, account.balance)
