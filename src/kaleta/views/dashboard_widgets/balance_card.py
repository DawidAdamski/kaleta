# SPDX-License-Identifier: AGPL-3.0-or-later
"""Balance card — the dashboard's hero figure plus its per-account breakdown.

Replaces the ``total_balance`` KPI widget (artboard ``1c``): one 54px mono
figure with muted decimals, the delta since the reference date, and the
accounts that make it up as quiet tiles underneath. Net worth and the
30-day prediction live in the month card's footer, where ``1c`` puts them.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence

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
from kaleta.views.theme import CARD_SUBTITLE, DASH_CARD, INK


class AccountLike(Protocol):
    """What the tiles need of an account — name and balance, nothing else."""

    name: str
    balance: Decimal


#: Accounts shown as tiles under the hero before the rest collapse into one.
_MAX_ACCOUNT_CHIPS = 3


def top_accounts(
    accounts: Sequence[AccountLike], limit: int = _MAX_ACCOUNT_CHIPS
) -> tuple[list[AccountLike], int, Decimal]:
    """The *limit* largest accounts, plus how many and how much they leave out.

    The hero sums every account, so the tiles must say what they omit or they
    read as a breakdown that does not add up. Ordering is by balance, not by
    name: three alphabetical accounts out of six explain nothing.
    """
    ranked = sorted(accounts, key=lambda a: a.balance, reverse=True)
    shown, rest = ranked[:limit], ranked[limit:]
    return shown, len(rest), sum((a.balance for a in rest), start=Decimal("0"))


def _account_chip(name: str, balance: Decimal) -> None:
    with ui.column().classes("k-account-chip gap-0.5 rounded-lg px-3.5 py-3 flex-1 min-w-32"):
        ui.label(name).classes(f"{CARD_SUBTITLE} truncate")
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
    accounts = await AccountService(session).list()

    with ui.card().classes(f"{DASH_CARD} justify-between"):
        with ui.column().classes("gap-1 w-full"):
            ui.label(t("dashboard.total_balance")).classes("k-eyebrow")
            hero_figure(total)
            ui.label(format_kpi_trend(delta)).classes(f"text-xs {trend_class(delta)}")

        shown, hidden, hidden_total = top_accounts(accounts)
        with ui.row().classes("w-full gap-2.5 flex-wrap mt-5"):
            for account in shown:
                _account_chip(account.name, account.balance)
            if hidden:
                _account_chip(t("dashboard.other_accounts", count=hidden), hidden_total)
