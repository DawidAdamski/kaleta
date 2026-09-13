# SPDX-License-Identifier: AGPL-3.0-or-later
"""Widget catalog — types, registration, and default widget order."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

WidgetSize = tuple[int, int]  # (cols, rows) in the 4-column dashboard grid

RenderFn = Callable[["AsyncSession", bool], Awaitable[None]]


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
