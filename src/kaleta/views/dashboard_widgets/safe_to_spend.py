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
from kaleta.views.dashboard_widgets.registry import RenderContext, register
from kaleta.views.theme import (
    DASH_CARD,
    HERO_LEGEND,
    HERO_RATE,
    MONO,
    SPLIT_BAR_HERO,
)

#: The bar's three segments, in the order they are drawn. All three tones are
#: this artboard's own: `3b`'s balance-sheet bar has `--asset` and
#: `--asset-soft` for its two greens, so `--ink` stays the ink `1c` draws here.
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


def eyebrow_label(stats: SafeToSpend) -> str:
    """ "Safe to spend · 28 days left", the one line artboard `1f` puts above
    the figure — the question and its denominator together, so the figure
    below has nothing between it and the eyebrow.
    """
    days = stats.days_left
    return t(plural_key("dashboard.sts_eyebrow", days), days=days)


def rate_line(stats: SafeToSpend) -> str:
    """ "69,36 zł a day. You've been averaging 74,80 zł." — one sentence.

    The artboard sets the pace and the habit in the same breath, because
    the second is what makes the first mean anything. A month with nothing
    left says how far past the end it is in place of the pace.
    """
    if stats.spendable:
        return t(
            "dashboard.sts_rate_line",
            amount=fmt_number(stats.per_day),
            avg=fmt_number(stats.trailing_avg_per_day),
        )
    return t(
        "dashboard.sts_over_line",
        amount=fmt_number(-stats.free),
        avg=fmt_number(stats.trailing_avg_per_day),
    )


def render_hero(stats: SafeToSpend) -> None:
    """The card's body, given the figures. Separate so the mobile bands and
    the desktop widget draw the same thing from the same data."""
    with ui.column().classes("w-full gap-0"):
        ui.label(eyebrow_label(stats)).classes("k-eyebrow")
        # 46px/400 at -.04em on a phone, which is what artboard `1f` sets
        # this hero at; the wider sizes are for a window that has the room.
        with ui.element("div").classes("mt-2.5"):
            hero_figure(
                stats.free,
                size="text-[46px] md:text-[64px]",
                weight="font-normal",
                tracking="tracking-[-.04em]",
            )
        # Above the bar, not under it: the artboard's order is figure, what
        # it means per day, then how it is made up.
        ui.label(rate_line(stats)).classes(f"{HERO_RATE} mt-2.5")

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
        with ui.element("div").classes(f"{SPLIT_BAR_HERO} w-full mt-[18px]"):
            for (pct, amount), (label_key, tone) in zip(shares, _SEGMENTS, strict=True):
                if pct <= 0:
                    continue
                seg = ui.element("div").classes(f"k-split-seg {tone}").style(f"width:{pct:.4f}%")
                seg.props["aria-label"] = f"{t(label_key)}: {fmt_number(amount)}"
        # Three labels spread across the bar's width, the way the artboard
        # draws them: no swatches, because each one sits over the segment it
        # names and the bar is read left to right.
        with ui.row().classes("w-full justify-between gap-3 no-wrap mt-[9px]"):
            for (_pct, amount), (label_key, _tone) in zip(shares, _SEGMENTS, strict=True):
                with ui.row().classes(f"{HERO_LEGEND} items-baseline gap-1.5 no-wrap"):
                    ui.label(t(label_key))
                    ui.label(fmt_number(amount)).classes(MONO)


@register(
    "safe_to_spend",
    "dashboard_widgets.safe_to_spend",
    "savings",
    (2, 2),
    ((2, 2), (4, 2)),
)
async def render_safe_to_spend(session: AsyncSession, ctx: RenderContext) -> None:
    stats = await ReportService(session).safe_to_spend()
    if ctx.narrow:
        # Flat on the ground, as artboard `1f` draws it: the hero is the
        # first thing on the page and there is nothing beside it for a card
        # to hold it apart from. On the desktop grid the same figure is one
        # widget among a dozen, and a card-less one would read as a hole.
        with ui.column().classes("w-full gap-0"):
            render_hero(stats)
        return
    with ui.card().classes(f"{DASH_CARD} gap-0"):
        render_hero(stats)
