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
from typing import TYPE_CHECKING, Any

from kaleta.i18n import t
from kaleta.views.components.amount_label import spaced_thousands
from kaleta.views.reports.constants import (
    COLUMNS,
    DATE_PRESETS,
    DIMENSIONS,
    METRICS,
    TX_TYPES,
    column_unavailable_reason,
)

if TYPE_CHECKING:  # import-linter excludes typing-only imports
    from kaleta.services.report_columns import DerivedLine
    from kaleta.services.saved_report_service import Column

#: The headers no language spells differently: a rank is a number sign and a
#: change is a delta in every locale the app ships.
_RANK_HEAD = "#"
_CHANGE_HEAD = "Δ"
_CHANGE_PCT_HEAD = "Δ %"


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


def series_label(state: dict[str, Any]) -> str:
    """ "Month", or the affordance that offers a second dimension.

    A blank where the word would go reads as a missing value; "by …" reads as
    an invitation, which is what an optional part of a sentence should look
    like when it has not been used yet.
    """
    if not state["series"]:
        return t("reports.series_none")
    return _label(DIMENSIONS, state["series"])


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


def column_label(column: str, window: int) -> str:
    """One derived column's name as the sentence says it: "3-month average"."""
    for key, label_key in COLUMNS:
        if key == column:
            return t(label_key, window=window)
    return "—"


def active_columns(state: dict[str, Any]) -> list[Column]:
    """The picked columns the query in hand can answer, in table order.

    The view's side of ``ReportConfig.active_columns``: a moving average
    picked on a monthly report and left behind when the grouping changed to
    Category is not named in the sentence, because it will not be drawn.
    """
    return [
        key
        for key, _label_key in COLUMNS
        if key in state["columns"]
        and column_unavailable_reason(key, state["dimension"], state["series"]) is None
    ]


def columns_label(state: dict[str, Any]) -> str:
    """ "share and 3-month average", or the affordance that offers columns.

    Like the second dimension, an unused optional clause reads as an
    invitation rather than as a blank.
    """
    names = [column_label(key, int(state["window"])) for key in active_columns(state)]
    if not names:
        return t("reports.columns_none")
    if len(names) == 1:
        return names[0]
    return f"{', '.join(names[:-1])} {t('reports.sentence_and')} {names[-1]}"


@dataclass(frozen=True, slots=True)
class SentenceSlots:
    """What the seven clickable parts of the sentence currently read."""

    metric: str
    dimension: str
    series: str
    types: str
    period: str
    top_n: str
    columns: str


def slot_labels(state: dict[str, Any]) -> SentenceSlots:
    return SentenceSlots(
        metric=metric_label(state),
        dimension=dimension_label(state),
        series=series_label(state),
        types=types_label(state),
        period=period_label(state),
        top_n=top_n_label(state),
        columns=columns_label(state),
    )


def chart_title(state: dict[str, Any]) -> str:
    """ "Expense by Category · This Year" — what the chart below is of.

    With a moving average on, the window rides at the end — *…, 3-month
    average* — so a dashed line on the chart says what it is averaging.
    """
    title = t(
        "reports.chart_title",
        types=types_label(state),
        dimension=dimension_label(state),
        period=period_label(state),
    )
    if "moving_avg" in active_columns(state):
        title = f"{title}, {column_label('moving_avg', int(state['window']))}"
    return title


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


def derived_headers(columns: Sequence[str], window: int) -> list[str]:
    """The table headers for the derived columns: Share, #, Δ, Δ %, MA(3).

    A change is two headers — its amount and its percent — which is why this
    returns a flat list rather than one header per column.
    """
    headers: list[str] = []
    for column in columns:
        if column == "share":
            headers.append(t("reports.col_share").capitalize())
        elif column == "rank":
            headers.append(_RANK_HEAD)
        elif column == "change":
            headers.extend([_CHANGE_HEAD, _CHANGE_PCT_HEAD])
        elif column == "moving_avg":
            headers.append(t("reports.col_head_ma", window=window))
    return headers


def _amount(value: float | None, *, signed: bool = False) -> str:
    """A figure in the tabular form the rows use; an em dash when it does not exist."""
    if value is None:
        return "—"
    return spaced_thousands(f"{value:+,.2f}" if signed else f"{value:,.2f}")


def derived_texts(line: DerivedLine, index: int, columns: Sequence[str]) -> list[str]:
    """What one cell's derived columns read, in the order of ``derived_headers``.

    A percent change from zero is an em dash, not ``inf`` — there is no
    baseline for it to be a percentage of.
    """
    texts: list[str] = []
    for column in columns:
        if column == "share" and line.share is not None:
            texts.append(f"{line.share[index]:.0f}%")
        elif column == "rank" and line.rank is not None:
            texts.append(str(line.rank[index]))
        elif column == "change" and line.change is not None and line.change_pct is not None:
            pct = line.change_pct[index]
            texts.append(_amount(line.change[index], signed=True))
            texts.append("—" if pct is None else f"{pct:+.0f}%")
        elif column == "moving_avg" and line.moving_avg is not None:
            texts.append(_amount(line.moving_avg[index]))
    return texts
