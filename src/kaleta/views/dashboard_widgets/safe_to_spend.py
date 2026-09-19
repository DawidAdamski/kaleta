# SPDX-License-Identifier: AGPL-3.0-or-later
"""Safe-to-spend hero (artboard 1f).

The phone dashboard answers one question before any other — *am I on track
this month?* — and a balance cannot answer it, because a balance does not
know that the rent leaves on the 28th. This card carries the one figure that
does: income minus what is already promised minus what is already gone, with
a three-segment bar behind it showing which of the three is the big one.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from nicegui import ui

from kaleta.i18n import plural_key, t
from kaleta.services import ReportService
from kaleta.services.report_service import SafeToSpend
from kaleta.views.dashboard_widgets.helpers import fmt_number, hero_figure
from kaleta.views.dashboard_widgets.registry import register
from kaleta.views.theme import (
    AMOUNT_EXPENSE,
    CARD_SUBTITLE,
    DASH_CARD,
    INK,
    MONO,
    MUTED,
    SPLIT_BAR_HERO,
)

#: The bar's three segments, in the order they are drawn. The tone classes are
#: the balance-sheet bar's from artboard 3b plus two of this artboard's own.
_SEGMENTS: tuple[tuple[str, str], ...] = (
    ("dashboard.sts_committed", "k-split--ink"),
    ("dashboard.sts_spent", "k-split--spent"),
    ("dashboard.sts_free", "k-split--free"),
)


@dataclass(frozen=True)
class HeroSplit:
    """The three shares of the bar, as percentages that add up to 100."""

    committed: float
    spent: float
    free: float


def hero_split(stats: SafeToSpend) -> HeroSplit | None:
    """Percentages for the bar, or ``None`` when there is no bar to draw.

    ``free`` is clamped at zero: a month already overspent has nothing left
    to colour, and a negative width would push the other two segments past
    the end of the track. The figure above the bar still says how far over.
    """
    parts = [max(float(value), 0.0) for value in (stats.committed, stats.spent, stats.free)]
    total = sum(parts)
    if total <= 0:
        return None
    committed, spent, free = (part / total * 100 for part in parts)
    return HeroSplit(committed=committed, spent=spent, free=free)


def days_left_label(stats: SafeToSpend) -> str:
    """ "21 days left" — the denominator of the per-day figure, in words."""
    days = stats.days_left
    return t(plural_key("dashboard.sts_days_left", days), days=days)


def render_hero(stats: SafeToSpend) -> None:
    """The card's body, given the figures. Separate so the mobile bands and
    the desktop widget draw the same thing from the same data."""
    with ui.column().classes("w-full gap-1"):
        ui.label(t("dashboard.safe_to_spend")).classes("k-eyebrow")
        # 46px/400 at -.04em on a phone, which is what artboard `1f` sets
        # this hero at; the wider sizes are for a window that has the room.
        hero_figure(
            stats.free,
            size="text-[46px] md:text-[64px]",
            weight="font-normal",
            tracking="tracking-[-.04em]",
        )
        ui.label(days_left_label(stats)).classes(CARD_SUBTITLE)

    split = hero_split(stats)
    if split is not None:
        shares = (
            (split.committed, stats.committed),
            (split.spent, stats.spent),
            # The legend reports what the segment draws, and the segment is
            # clamped — an overspent month shows no free money, not less
            # than none. How far over is the figure above the bar.
            (split.free, max(stats.free, Decimal("0.00"))),
        )
        # A plain div, not ui.row: `.nicegui-row` puts a gap between children
        # and a gap here would be read as a fourth segment.
        with ui.element("div").classes(f"{SPLIT_BAR_HERO} w-full mt-4"):
            for (pct, amount), (label_key, tone) in zip(shares, _SEGMENTS, strict=True):
                if pct <= 0:
                    continue
                seg = ui.element("div").classes(f"k-split-seg {tone}").style(f"width:{pct:.4f}%")
                seg.props["aria-label"] = f"{t(label_key)}: {fmt_number(amount)}"
        with ui.row().classes("w-full gap-4 flex-wrap mt-2"):
            for (_pct, amount), (label_key, tone) in zip(shares, _SEGMENTS, strict=True):
                with ui.row().classes("items-center gap-1.5"):
                    ui.element("div").classes(f"k-split-dot {tone}")
                    ui.label(t(label_key)).classes(f"{MUTED} text-xs")
                    ui.label(fmt_number(amount)).classes(f"{MONO} text-xs")

    with ui.row().classes("w-full items-baseline justify-between gap-3 mt-4 flex-wrap"):
        # "-14.29 zł a day" is not a budget, it is an overdraft. A month with
        # nothing left says how far past the end it is instead.
        if stats.spendable:
            headline = t("dashboard.sts_per_day", amount=fmt_number(stats.per_day))
            tone = INK
        else:
            headline = t("dashboard.sts_over", amount=fmt_number(-stats.free))
            tone = AMOUNT_EXPENSE
        ui.label(headline).classes(f"{MONO} {tone} text-[17px] font-medium")
        ui.label(
            t("dashboard.sts_trailing", amount=fmt_number(stats.trailing_avg_per_day))
        ).classes(CARD_SUBTITLE)


@register(
    "safe_to_spend",
    "dashboard_widgets.safe_to_spend",
    "savings",
    (2, 2),
    ((2, 2), (4, 2)),
)
async def render_safe_to_spend(session: AsyncSession, is_dark: bool) -> None:  # noqa: ARG001
    stats = await ReportService(session).safe_to_spend()
    with ui.card().classes(f"{DASH_CARD} justify-between"):
        render_hero(stats)
