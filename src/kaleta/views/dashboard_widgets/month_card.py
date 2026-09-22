# SPDX-License-Identifier: AGPL-3.0-or-later
"""Month card — in, out and net for the current month, plus savings pace.

Replaces the ``month_income``, ``month_expenses``, ``month_net`` and
``savings_rate_kpi`` KPI widgets (artboard ``1c``): three 26px mono figures
side by side, a ``.k-pace`` bar carrying the kept-share of income with a
tick at the target, and — below a hairline — the two slow figures that
used to be cards of their own, ``predicted_30d`` and ``net_worth``.
"""

from __future__ import annotations

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
from kaleta.views.dashboard_widgets.helpers import fmt_number
from kaleta.views.dashboard_widgets.registry import RenderContext, register
from kaleta.views.theme import (
    AMOUNT_EXPENSE,
    AMOUNT_INCOME,
    CARD_CAPTION,
    CARD_SUBTITLE,
    DASH_CARD,
    INK,
    PACE_BAR_MONTH,
)


def _footer_stat(label: str, value: str) -> None:
    with ui.column().classes("gap-0 min-w-0"):
        ui.label(label).classes(CARD_CAPTION)
        ui.label(value).classes(f"k-mono {INK} text-[17px] font-medium")


def _figure(label: str, value: str, amount_cls: str) -> None:
    """One of the three month figures.

    The floor and the smaller type below ``md`` are what keep the row inside
    a 390px screen: a mono figure does not shrink with its column, so with
    ``min-w-0`` alone the third one simply hung over the edge. Above ``md``
    both revert and the card is the 1c card unchanged.
    """
    with ui.column().classes("gap-0.5 flex-1 min-w-[120px] md:min-w-0"):
        ui.label(label).classes(CARD_SUBTITLE)
        ui.label(value).classes(
            f"k-mono {amount_cls} text-[22px] md:text-[26px] font-medium tracking-tight"
        )


def _band_figure(label: str, value: str, amount_cls: str) -> None:
    """One of the three figures as artboard `1f` sets them in the Month band.

    11px label over a 500/18 mono figure, three abreast on the ground. The
    smaller figure is what lets all three sit on one line of a 350px content
    width without the floor `_figure` needs — and a third of that width is
    room for five digits, which is every household figure this app has.
    """
    with ui.column().classes("gap-0.5 flex-1 min-w-0"):
        ui.label(label).classes(f"{CARD_SUBTITLE} !text-[11px]")
        ui.label(value).classes(f"k-mono {amount_cls} text-[18px] font-medium mt-0.5")


async def _render_month_band(session: AsyncSession) -> None:
    """The Month band's head on a phone: three figures, no card (artboard `1f`).

    What the wide card carries and this does not is the pace bar and the two
    footer figures — and none of the three is dropped from the page, because
    the Watch band two bands down already says the savings rate, the 30-day
    balance and the net worth in plain type. Saying them again here would be
    the same three figures twice on one screen.
    """
    point = await ReportService(session).current_month_point()
    with ui.row().classes("w-full gap-x-4 gap-y-2 no-wrap"):
        _band_figure(t("dashboard.month_in"), fmt_number(point.income), AMOUNT_INCOME)
        _band_figure(t("dashboard.month_out"), fmt_number(point.expenses), AMOUNT_EXPENSE)
        _band_figure(t("dashboard.net"), fmt_number(point.savings), INK)


def _pace_bar(point: SavingsRatePoint) -> None:
    """Savings-rate track filled to the kept share, with a tick at the target."""
    rate = point.rate_pct
    target = float(SAVINGS_RATE_TARGET_PCT)
    filled = 0.0 if rate is None else max(0.0, min(float(rate), 100.0))
    fill_colour = (
        "var(--k-income)" if point.meets_target(SAVINGS_RATE_TARGET_PCT) else "var(--k-warning)"
    )

    with ui.row().classes("w-full items-baseline justify-between mt-5"):
        ui.label(
            t("dashboard.savings_kept_none")
            if rate is None
            else t("dashboard.savings_kept", pct=f"{float(rate):.1f}")
        ).classes(f"{CARD_SUBTITLE} !text-[11.5px]")
        ui.label(t("dashboard.savings_target", pct=f"{target:.0f}")).classes(
            f"{CARD_SUBTITLE} !text-[11.5px]"
        )

    with ui.element("div").classes(f"{PACE_BAR_MONTH} w-full mt-1.5"):
        ui.element("div").classes("k-pace__fill").style(
            f"width:{filled:.2f}%;background:{fill_colour}"
        )
        ui.element("div").classes("k-pace__tick").style(f"left:{min(target, 100.0):.2f}%")


@register(
    "month_card",
    "dashboard_widgets.month_card",
    "swap_vert",
    (2, 2),
    ((2, 2), (4, 2)),
)
async def render_month_card(session: AsyncSession, ctx: RenderContext) -> None:
    if ctx.narrow:
        await _render_month_band(session)
        return
    point = await ReportService(session).current_month_point()
    income, expenses, net = point.income, point.expenses, point.savings
    summary = await NetWorthService(session).get_summary(history_months=2)
    forecast = await ForecastService(session).forecast_account(account_id=None, horizon_days=30)
    # No Prophet, or too little history: the service says so by having no
    # prediction to give, and the footer renders an em dash for it.
    predicted = forecast.predicted_balance_30d

    # `gap-0`: artboard `1c` sets every offset in this card as a margin, and
    # a card gap adds itself to each of them.
    #
    # `!h-auto` beats the grid's `height:100%`, which stretches a card to the
    # tallest in its row. On the artboard both top cards hold the same amount
    # and the question never comes up; on a ledger with four accounts the
    # balance card grows a second row of tiles, and 70px of stretch has to go
    # somewhere — spread between the rows it loosens the whole card, and
    # gathered above the footer it is a hole. Neither is the card the artboard
    # draws, so the card is the height of what is in it and the spare height
    # stays outside as ground.
    with ui.card().classes(f"{DASH_CARD} gap-0 !h-auto"):
        with ui.column().classes("gap-1 w-full"):
            ui.label(t("dashboard_widgets.month_card")).classes("k-eyebrow")
            # No `no-wrap`: three 26px figures held on one line pushed the
            # card past the edge of a 390px screen — by a single pixel, which
            # is still a page that scrolls sideways. With room they stay on
            # one line, so nothing changes on a desktop.
            with ui.row().classes("w-full gap-x-7 gap-y-2 mt-3.5"):
                # "In" / "Out", not "Income" / "Expense": three figures share
                # a half-width card, and the artboard spends the room on the
                # figures rather than on the words above them.
                _figure(t("dashboard.month_in"), fmt_number(income), AMOUNT_INCOME)
                _figure(t("dashboard.month_out"), fmt_number(expenses), AMOUNT_EXPENSE)
                _figure(t("dashboard.net"), fmt_number(net), INK)

        _pace_bar(point)

        # The artboard's `flex:1;min-height:14px` — where a taller neighbour's
        # spare height goes, and a floor under it when there is none to give.
        ui.element("div").classes("flex-1 min-h-[14px]")

        with ui.row().classes("w-full gap-6 pt-[18px] k-card-footer flex-wrap"):
            _footer_stat(
                t("dashboard.balance_30"),
                "—" if predicted is None else fmt_number(predicted),
            )
            _footer_stat(
                t("dashboard_widgets.net_worth"),
                fmt_number(summary.net_worth),
            )
