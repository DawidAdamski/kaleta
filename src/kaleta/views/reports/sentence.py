# SPDX-License-Identifier: AGPL-3.0-or-later
"""The report query as a readable sentence (artboard 3e).

The builder used to ask for the query through two drop zones and a filter
panel, which said what the controls were but never what the question was.
The same state reads as one line — *Show Total Amount grouped by Category for
Expense over This Year, top 10.* — and every underlined part of it is a
control. These helpers turn the state into that line's words; the widgets
that make them clickable live in ``config_zone``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from kaleta.i18n import t
from kaleta.views.components.amount_label import spaced_thousands
from kaleta.views.reports.constants import DATE_PRESETS, DIMENSIONS, METRICS, TX_TYPES


def _label(rows: Sequence[tuple[str, ...]], key: str) -> str:
    """The translated label for ``key``, or an em dash when it is unknown.

    Every table in ``constants`` starts ``(key, label_key, …)``; only the tail
    differs, so one lookup serves all of them.
    """
    for row in rows:
        if row[0] == key:
            return t(row[1])
    return "—"


def metric_label(state: dict[str, Any]) -> str:
    return _label(METRICS, state["metric"])


def dimension_label(state: dict[str, Any]) -> str:
    return _label(DIMENSIONS, state["dimension"])


def types_label(state: dict[str, Any]) -> str:
    """ "Expense", "Expense + Income", or "all types" when nothing is excluded.

    Naming all three is technically right and says nothing: a filter that
    excludes nothing is better read as the absence of a filter.
    """
    selected = [
        key for key, _label_key, _icon, _colour in TX_TYPES if key in state["transaction_types"]
    ]
    if not selected:
        return "—"
    if len(selected) == len(TX_TYPES):
        return t("reports.sentence_types_all")
    return " + ".join(_label(TX_TYPES, key) for key in selected)


def period_label(state: dict[str, Any]) -> str:
    """The preset's own name, or the two dates when the preset is custom.

    Deliberately the preset's *name* and not the dates it resolves to: the
    engine owns that arithmetic, and a sentence that restated it would be one
    more place for the two to drift apart.
    """
    if state["date_preset"] != "custom":
        return _label(DATE_PRESETS, state["date_preset"])
    start, end = state["date_from"], state["date_to"]
    if start and end:
        return f"{start} – {end}"
    if start:
        return t("reports.sentence_from_date", date=start)
    if end:
        return t("reports.sentence_to_date", date=end)
    return _label(DATE_PRESETS, "custom")


def top_n_label(state: dict[str, Any]) -> str:
    """``top_n`` of 0 means no limit, which "top 0" would read as the opposite."""
    top_n = int(state["top_n"] or 0)
    return str(top_n) if top_n > 0 else t("reports.sentence_no_limit")


@dataclass(frozen=True, slots=True)
class SentenceSlots:
    """What the five clickable parts of the sentence currently read."""

    metric: str
    dimension: str
    types: str
    period: str
    top_n: str


def slot_labels(state: dict[str, Any]) -> SentenceSlots:
    return SentenceSlots(
        metric=metric_label(state),
        dimension=dimension_label(state),
        types=types_label(state),
        period=period_label(state),
        top_n=top_n_label(state),
    )


def chart_title(state: dict[str, Any]) -> str:
    """ "Expense by Category · This Year" — what the chart below is of."""
    return t(
        "reports.chart_title",
        types=types_label(state),
        dimension=dimension_label(state),
        period=period_label(state),
    )


def result_total(values: list[float], *, metric: str) -> str | None:
    """What the card's title line says the result adds up to, or nothing.

    Beside `share_percents`, because the two are the same question asked
    twice — what the rows come to, and what each one is of that — and a
    caption's arithmetic sitting inline in the zone that draws it is
    arithmetic no test can reach.

    ``None`` for the average metric: adding twelve monthly averages
    together gives a figure that is not the average of anything, and a
    caption reading "total" over it would be a lie in mono. Sums and
    counts both add up to something a reader can use.
    """
    if metric == "avg":
        return None
    return spaced_thousands(f"{sum(values):,.2f}")


def bar_widths(values: list[float]) -> list[float]:
    """Each bar's length as a percentage of the longest one.

    Not the same question as `share_percents`: a share is of the total, a
    width is of the widest row, and a ranking of two rows at 60 and 40 draws
    100% and 67% while sharing 60% and 40%. Zero everywhere when nothing has
    a size — a list of zeroes has no longest row to be a fraction of.
    """
    widest = max((abs(v) for v in values), default=0.0)
    if widest <= 0:
        return [0.0 for _ in values]
    return [abs(v) / widest * 100 for v in values]


def share_percents(values: list[float]) -> list[float]:
    """Each value's share of the total, for the bar labels.

    Shares of a total that is zero or below do not exist — a mix of signs
    summing to nothing has no meaningful proportions — so every share is 0
    rather than a division that happens to survive.
    """
    total = sum(abs(v) for v in values)
    if total <= 0:
        return [0.0 for _ in values]
    return [abs(v) / total * 100 for v in values]
