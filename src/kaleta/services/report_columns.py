# SPDX-License-Identifier: AGPL-3.0-or-later
"""Derived report columns: share, rank, change and moving average.

A grouped report says what the numbers are; these say where they are going.
Every derivation runs over the rows the query already returned — a few
hundred cells at most — so both SQL dialects stay untouched and the
arithmetic lives here, in pure functions a test can reach without a database.

On a one-dimensional report the columns sit beside ``values``. On a pivot,
change and moving average run **per row along the series axis** (so
*Category by Month* is month-over-month for each category), while share and
rank are taken **within each series column**: each month's shares add up to
100 %, the reading the one-dimensional bar view gives a single period.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise

from kaleta.exceptions import ValidationError
from kaleta.services.saved_report_service import (
    Column,
    Dimension,
    PivotResult,
    ReportResult,
)


@dataclass(frozen=True)
class DerivedLine:
    """The derived values of one line, aligned with its cells.

    A line is the whole result on a one-dimensional report and one row on a
    pivot. A column that was not asked for is ``None``; inside an asked-for
    column, ``None`` is a value that does not exist — the change into the
    first period, a percent change from zero, an average over fewer periods
    than its window.
    """

    share: tuple[float, ...] | None = None  # percent
    rank: tuple[int, ...] | None = None  # 1 = largest
    change: tuple[float | None, ...] | None = None
    change_pct: tuple[float | None, ...] | None = None
    moving_avg: tuple[float | None, ...] | None = None


@dataclass(frozen=True)
class DerivedResult:
    columns: tuple[Column, ...]
    window: int
    #: One line for a ``ReportResult``; one per pivot row, in row order.
    lines: tuple[DerivedLine, ...]


# ── Time axis ─────────────────────────────────────────────────────────────────


def _period_key(label: str, axis: Dimension) -> int | None:
    """A label as a count of periods, so that neighbours differ by one."""
    try:
        if axis == "month":
            year, month = label.split("-")
            return int(year) * 12 + int(month) - 1
        if axis == "year":
            return int(label)
    except ValueError:
        return None
    return None


def _period_label(key: int, axis: Dimension) -> str:
    if axis == "month":
        return f"{key // 12:04d}-{key % 12 + 1:02d}"
    return str(key)


def _full_axis(labels: Sequence[str], axis: Dimension) -> list[str] | None:
    """Every period from the first label to the last, or None if one is not a period."""
    keys = [_period_key(label, axis) for label in labels]
    if not keys:
        return []
    known = [key for key in keys if key is not None]
    if len(known) != len(keys):
        return None
    return [_period_label(key, axis) for key in range(min(known), max(known) + 1)]


def fill_time_axis(
    result: ReportResult | PivotResult, axis: Dimension
) -> ReportResult | PivotResult:
    """The result in chronological order, with every missing period as a zero.

    A category with no spend in March reads as a drop to nothing in March,
    not as a February followed directly by an April. The axis is the
    grouping on a one-dimensional report and the series on a pivot; a label
    that is not a period of ``axis`` leaves the result as it was.
    """
    if isinstance(result, PivotResult):
        series = _full_axis(result.series_labels, axis)
        if series is None:
            return result
        position = {label: index for index, label in enumerate(result.series_labels)}
        cells = [
            [row[position[label]] if label in position else 0.0 for label in series]
            for row in result.cells
        ]
        return dataclasses.replace(
            result,
            series_labels=series,
            cells=cells,
            series_totals=[sum(column) for column in zip(*cells, strict=True)] if cells else [],
        )

    labels = _full_axis(result.labels, axis)
    if labels is None:
        return result
    by_label = dict(zip(result.labels, result.values, strict=True))
    return dataclasses.replace(
        result, labels=labels, values=[by_label.get(label, 0.0) for label in labels]
    )


# ── Derivations ───────────────────────────────────────────────────────────────


def shares(values: Sequence[float]) -> tuple[float, ...]:
    """Each value's size as a percent of the sizes' total.

    Sizes, not signed values, as the bar view reads them (`KAL-RPT-002`); a
    total of nothing has no shares to give, so every share is zero.
    """
    total = sum(abs(value) for value in values)
    if total <= 0:
        return tuple(0.0 for _ in values)
    return tuple(abs(value) / total * 100 for value in values)


def ranks(values: Sequence[float]) -> tuple[int, ...]:
    """Each value's place by size, largest first; ties share a place.

    Competition ranking — two firsts are followed by a third — so a rank
    always says how many values are bigger than this one.
    """
    sizes = [abs(value) for value in values]
    return tuple(1 + sum(other > size for other in sizes) for size in sizes)


def changes(values: Sequence[float]) -> tuple[float | None, ...]:
    """The difference from the previous period; the first has none."""
    return tuple(
        None if index == 0 else value - values[index - 1] for index, value in enumerate(values)
    )


def percent_changes(values: Sequence[float]) -> tuple[float | None, ...]:
    """The change as a percent of the previous period.

    ``None`` from a zero: going from nothing to something is not an infinite
    rise, it is a rise with no baseline to be a percentage of.
    """
    result: list[float | None] = [None]
    for previous, value in pairwise(values):
        result.append(None if previous == 0 else (value - previous) / abs(previous) * 100)
    return tuple(result[: len(values)])


def moving_averages(values: Sequence[float], window: int) -> tuple[float | None, ...]:
    """The trailing mean of the last ``window`` periods, this one included.

    ``None`` until a full window of history exists: the mean of one month is
    that month, and calling it a three-month average would say otherwise.
    """
    if window < 1:
        raise ValidationError("A moving average needs a window of at least one period.")
    return tuple(
        None if index + 1 < window else sum(values[index + 1 - window : index + 1]) / window
        for index in range(len(values))
    )


def _line(
    values: Sequence[float],
    columns: Sequence[Column],
    window: int,
    *,
    share: tuple[float, ...] | None = None,
    rank: tuple[int, ...] | None = None,
) -> DerivedLine:
    wants_change = "change" in columns
    return DerivedLine(
        share=share,
        rank=rank,
        change=changes(values) if wants_change else None,
        change_pct=percent_changes(values) if wants_change else None,
        moving_avg=moving_averages(values, window) if "moving_avg" in columns else None,
    )


def derive(
    result: ReportResult | PivotResult,
    columns: Sequence[Column],
    window: int,
) -> DerivedResult:
    """The asked-for columns, computed over the result as it stands.

    The caller decides which columns the query can answer and fills the time
    axis first (``ReportConfig.active_columns``, ``fill_time_axis``): this
    function only does arithmetic, along whatever order the cells are in.
    """
    wanted = tuple(columns)
    if isinstance(result, PivotResult):
        # Share and rank are across the rows of each series column; change
        # and moving average are along each row. Transposed once, both ways.
        by_column = [list(column) for column in zip(*result.cells, strict=True)]
        column_shares = [shares(column) for column in by_column] if "share" in wanted else None
        column_ranks = [ranks(column) for column in by_column] if "rank" in wanted else None
        lines = tuple(
            _line(
                row,
                wanted,
                window,
                share=None if column_shares is None else tuple(c[index] for c in column_shares),
                rank=None if column_ranks is None else tuple(c[index] for c in column_ranks),
            )
            for index, row in enumerate(result.cells)
        )
        return DerivedResult(columns=wanted, window=window, lines=lines)

    line = _line(
        result.values,
        wanted,
        window,
        share=shares(result.values) if "share" in wanted else None,
        rank=ranks(result.values) if "rank" in wanted else None,
    )
    return DerivedResult(columns=wanted, window=window, lines=(line,))
