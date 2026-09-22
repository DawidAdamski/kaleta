# SPDX-License-Identifier: AGPL-3.0-or-later
"""How a run of days is cut into weeks.

Two people can both be right about where a week starts. One reads a calendar:
a week is Monday to Sunday, and the first week of October began in September.
The other reads a statement: the month opens on the 1st and the weeks run in
sevens from there, so the last one is a stub of one to seven days.

``WeekStartMode`` names the two answers and ``week_bucket`` gives the one
bucket a day falls in. Everything that shows a weekly subtotal asks here, so
two screens cannot disagree about which week a transaction belongs to.

The ISO buckets are *not* clipped to the month the caller happened to ask
about: a Monday-to-Sunday week is seven days wide wherever it is read, and
trimming it would make the subtotal under it disagree with its own heading.
The month-relative buckets are clipped, because being inside one month is
what defines them.
"""

from __future__ import annotations

import calendar
import datetime
import enum
from collections.abc import Iterable
from dataclasses import dataclass

__all__ = [
    "DEFAULT_WEEK_START_MODE",
    "WeekBucket",
    "WeekStartMode",
    "coerce_mode",
    "week_bucket",
    "week_buckets",
]

#: A week's last day is six days after its first, not seven.
_SIX_DAYS = datetime.timedelta(days=6)


class WeekStartMode(enum.StrEnum):
    """Where a week begins."""

    #: Monday to Sunday, ISO 8601. Weeks cross month and year boundaries.
    ISO_MONDAY = "iso_monday"
    #: The 1st of the month opens week 1; every later week is seven days on,
    #: and the last one ends with the month.
    MONTH_DAY_1 = "month_day_1"


DEFAULT_WEEK_START_MODE = WeekStartMode.ISO_MONDAY


@dataclass(frozen=True, slots=True, order=True)
class WeekBucket:
    """One week, both ends inclusive.

    ``index`` is what a heading calls the week: the ISO week number under
    ``ISO_MONDAY``, and the 1-based ordinal inside the month under
    ``MONTH_DAY_1``.
    """

    start: datetime.date
    end: datetime.date
    index: int

    @property
    def days(self) -> int:
        """How many days the bucket spans — seven, or fewer for a stub."""
        return (self.end - self.start).days + 1

    def contains(self, day: datetime.date) -> bool:
        return self.start <= day <= self.end


def coerce_mode(raw: object) -> WeekStartMode:
    """The mode a stored value names, or the default when it names none.

    Storage is a JSON blob a user can edit and an older build may have
    written, so an unknown string must not take a screen down.
    """
    try:
        return WeekStartMode(str(raw))
    except ValueError:
        return DEFAULT_WEEK_START_MODE


def week_bucket(day: datetime.date, mode: WeekStartMode = DEFAULT_WEEK_START_MODE) -> WeekBucket:
    """The single week ``day`` belongs to under ``mode``."""
    if mode is WeekStartMode.MONTH_DAY_1:
        ordinal = (day.day - 1) // 7
        start = day.replace(day=ordinal * 7 + 1)
        last_of_month = day.replace(day=calendar.monthrange(day.year, day.month)[1])
        return WeekBucket(start=start, end=min(start + _SIX_DAYS, last_of_month), index=ordinal + 1)

    start = day - datetime.timedelta(days=day.weekday())
    return WeekBucket(start=start, end=start + _SIX_DAYS, index=day.isocalendar().week)


def week_buckets(
    dates: Iterable[datetime.date],
    mode: WeekStartMode = DEFAULT_WEEK_START_MODE,
) -> list[WeekBucket]:
    """Every distinct week the given days fall in, oldest first.

    Weeks nothing falls in are left out: the caller hands over the days it
    actually has, and an empty band under a heading is noise, not data.
    """
    buckets = {week_bucket(day, mode) for day in dates}
    return sorted(buckets)
