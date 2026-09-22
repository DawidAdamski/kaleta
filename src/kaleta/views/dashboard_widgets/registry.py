# SPDX-License-Identifier: AGPL-3.0-or-later
"""Widget catalog — types, registration, and default widget order."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

WidgetSize = tuple[int, int]  # (cols, rows) in the 4-column dashboard grid


@dataclass(frozen=True, slots=True)
class RenderContext:
    """What a widget is allowed to know about where it is being drawn.

    A widget used to be handed a bare ``is_dark``, which made the dark theme
    the only thing about its surroundings it could answer to. Artboard ``1f``
    asks three of them to draw differently on a phone — the Needs-attention
    card, the Latest rows, the Month band's bare type — so the width has to
    reach them too.

    A frozen dataclass rather than a second boolean: the signature is being
    changed across twenty-two modules either way, and the next thing a widget
    needs to know about its surroundings should not cost that again.

    ``narrow`` is a decision, not a measurement: ``dashboard._viewport_is_mobile``
    makes it once per page, server-side, and every widget on that page is drawn
    to the same answer. A widget is never told pixels, because a widget that
    knew its own width would be free to disagree with the page about which
    layout is being built.
    """

    is_dark: bool
    #: True when the page is the phone's stacked bands, not the desktop grid.
    narrow: bool = False


RenderFn = Callable[["AsyncSession", RenderContext], Awaitable[None]]


@dataclass(frozen=True)
class Widget:
    id: str
    title_key: str
    icon: str
    default_size: WidgetSize
    allowed_sizes: tuple[WidgetSize, ...]
    render: RenderFn = field(repr=False)
    #: Superseded by a merged card. Still rendered when a stored layout names
    #: it, so no saved dashboard breaks, but hidden from the Customize picker
    #: so nobody adds one back. Deleted once no stored layout references them.
    legacy: bool = False


WIDGETS: dict[str, Widget] = {}


def register(
    widget_id: str,
    title_key: str,
    icon: str,
    default_size: WidgetSize,
    allowed_sizes: tuple[WidgetSize, ...] | None = None,
    *,
    legacy: bool = False,
) -> Callable[[RenderFn], RenderFn]:
    sizes = allowed_sizes or (default_size,)
    if default_size not in sizes:
        raise ValueError(f"{widget_id}: default_size {default_size} not in allowed_sizes {sizes}")

    def wrap(fn: RenderFn) -> RenderFn:
        WIDGETS[widget_id] = Widget(
            id=widget_id,
            title_key=title_key,
            icon=icon,
            default_size=default_size,
            allowed_sizes=sizes,
            render=fn,
            legacy=legacy,
        )
        return fn

    return wrap


def cycle_size(current: WidgetSize, allowed: tuple[WidgetSize, ...]) -> WidgetSize:
    """Return the next allowed size after `current`, wrapping around."""
    try:
        idx = allowed.index(current)
    except ValueError:
        return allowed[0]
    return allowed[(idx + 1) % len(allowed)]


#: Which merged card each of the seven single-figure KPI widgets became, in
#: the order they used to appear. A stored layout naming any of these is
#: migrated on read (see ``layout.migrate_legacy_kpis``). The mapping is what
#: keeps the migration faithful: a user who kept only the month tiles gets the
#: month card, not both.
MERGED_KPI_FOR_LEGACY: dict[str, str] = {
    "total_balance": "balance_card",
    "month_income": "month_card",
    "month_expenses": "month_card",
    "month_net": "month_card",
    "predicted_30d": "month_card",
    "net_worth": "month_card",
    "savings_rate_kpi": "month_card",
}

#: The seven, as a tuple — the order above is the dashboard's old default.
LEGACY_KPI_WIDGETS: tuple[str, ...] = tuple(MERGED_KPI_FOR_LEGACY)

#: What those seven become.
MERGED_KPI_WIDGETS: tuple[str, ...] = tuple(dict.fromkeys(MERGED_KPI_FOR_LEGACY.values()))


class Band(StrEnum):
    """The four stacked bands of the phone dashboard (artboard 1f).

    A phone cannot show a 4-column grid, and a single column of equal cards
    is a scroll with no shape. The bands give it one: what is happening
    *now*, how the *month* is going, the slow figures you only *watch*, and
    *latest* — the log, which is not a metric and belongs under everything
    that is. A wide window gets the grid instead (artboard 1c).
    """

    NOW = "now"
    MONTH = "month"
    WATCH = "watch"
    LATEST = "latest"


#: Which band a widget belongs to on a phone. Anything unlisted falls into
#: ``MONTH`` — the band for "how is this month going", which is what most of
#: the catalog is about, and the safe place for a widget added later.
#:
#: Nothing maps to ``WATCH`` on purpose: that band is four figures in plain
#: type, not cards (see ``dashboard._render_watch_band``). Sending the slow
#: widgets there put a YTD card and two trend charts under the very figures
#: that summarise them, and said the year-to-date net twice.
BAND_OF: dict[str, Band] = {
    "safe_to_spend": Band.NOW,
    "wizard_actions": Band.NOW,
    "quick_actions": Band.NOW,
    "recent_transactions": Band.LATEST,
}

#: Band order on the page, top to bottom, with the i18n key of each heading.
BAND_ORDER: tuple[tuple[Band, str], ...] = (
    (Band.NOW, "dashboard.band_now"),
    (Band.MONTH, "dashboard.band_month"),
    (Band.WATCH, "dashboard.band_watch"),
    (Band.LATEST, "dashboard.band_latest"),
)


def band_of(widget_id: str) -> Band:
    """The band *widget_id* belongs to; ``MONTH`` when nothing says."""
    return BAND_OF.get(widget_id, Band.MONTH)


def bands_for_layout(layout: list[dict[str, Any]]) -> dict[Band, list[dict[str, Any]]]:
    """Group a stored layout into the four bands, keeping its order.

    Legacy widgets are dropped rather than banded: they are the seven
    single-figure KPIs that ``restyle-dashboard`` merged into two cards, kept
    alive only so an old stored layout still renders on the desktop grid. The
    phone layout is new and starts without that debt — and the Watch band
    already says three of the four figures they carried.
    """
    grouped: dict[Band, list[dict[str, Any]]] = {band: [] for band, _key in BAND_ORDER}
    for entry in layout:
        widget_id = entry.get("id")
        widget = WIDGETS.get(widget_id) if isinstance(widget_id, str) else None
        if widget is None or widget.legacy:
            continue
        grouped[band_of(widget.id)].append(entry)
    return grouped


#: The hero the phone dashboard always leads with, whether or not the stored
#: (desktop) layout carries it — see ``mobile_layout``.
HERO_WIDGET = "safe_to_spend"


def mobile_layout(layout: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The stored layout with the safe-to-spend hero guaranteed at its head.

    The hero is off by default on the desktop grid (it is a phone answer to a
    phone question), so a phone would otherwise never show it. Prepending it
    here rather than rendering it separately keeps it an ordinary banded
    widget — it cannot then appear twice for someone who did switch it on.
    """
    if any(entry.get("id") == HERO_WIDGET for entry in layout):
        return list(layout)
    hero = WIDGETS[HERO_WIDGET]
    return [
        {"id": HERO_WIDGET, "cols": hero.default_size[0], "rows": hero.default_size[1]},
        *layout,
    ]


def selectable_widgets() -> list[str]:
    """Widget ids offered in the Customize picker — everything but legacy."""
    return [wid for wid, w in WIDGETS.items() if not w.legacy]


DEFAULT_WIDGETS: list[str] = [
    "balance_card",
    "month_card",
    "wizard_actions",
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
