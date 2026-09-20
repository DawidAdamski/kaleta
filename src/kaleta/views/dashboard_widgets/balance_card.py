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
    fmt_number,
    format_kpi_trend,
    hero_figure,
    trend_class,
)
from kaleta.views.dashboard_widgets.registry import register
from kaleta.views.theme import CARD_CAPTION, DASH_CARD, INK

#: Accounts named under the hero before the rest collapse into one tile.
_MAX_ACCOUNT_TILES = 3


def _account_chip(name: str, balance: Decimal) -> None:
    with ui.column().classes("k-account-chip gap-0.5 rounded-[10px] px-3.5 py-3 flex-1 min-w-32"):
        ui.label(name).classes(f"{CARD_CAPTION} truncate")
        ui.label(fmt_number(balance)).classes(f"k-mono {INK} text-[16px] font-medium")


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
    accounts = await AccountService(session).balance_breakdown(_MAX_ACCOUNT_TILES)

    # `gap-0` for the same reason the offsets below are explicit: artboard
    # `1c` sets 12px under the eyebrow, 8px under the hero and 22px above the
    # tiles, and a card gap adds itself to every one of them. `!h-auto` for
    # the reason the month card beside it carries one: a card is the height of
    # what is in it, not of its neighbour.
    with ui.card().classes(f"{DASH_CARD} gap-0 !h-auto"):
        # Explicit offsets rather than one column gap: artboard `1c` sets
        # 12px under the eyebrow and 8px under the hero, which one gap cannot
        # be both of.
        with ui.column().classes("gap-0 w-full"):
            ui.label(t("dashboard_widgets.balance_card")).classes("k-eyebrow")
            with ui.element("div").classes("mt-3"):
                hero_figure(total)
            ui.label(format_kpi_trend(delta)).classes(f"text-[13px] mt-2 {trend_class(delta)}")

        with ui.row().classes("w-full gap-2.5 flex-wrap mt-[22px]"):
            for account in accounts.shown:
                _account_chip(account.name, account.balance)
            if accounts.hidden_count:
                _account_chip(
                    t("dashboard.other_accounts", count=accounts.hidden_count),
                    accounts.hidden_total,
                )
