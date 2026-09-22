# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for kaleta.core.weeks — how days are cut into weeks.

The month cases are the four month lengths a year can hold: 31, 30, 29 and 28
days, each under both modes. The expected bucket boundaries are the literals
from the plan's acceptance criteria, not values read back out of the helper.
"""

from __future__ import annotations

import datetime

import pytest

from kaleta.core.weeks import (
    DEFAULT_WEEK_START_MODE,
    WeekStartMode,
    coerce_mode,
    week_bucket,
    week_buckets,
)


def _days(year: int, month: int, last: int) -> list[datetime.date]:
    return [datetime.date(year, month, day) for day in range(1, last + 1)]


def _spans(buckets: list) -> list[tuple[str, str]]:
    return [(str(b.start), str(b.end)) for b in buckets]


class TestDefaults:
    def test_default_is_iso_monday(self) -> None:
        assert DEFAULT_WEEK_START_MODE is WeekStartMode.ISO_MONDAY

    @pytest.mark.parametrize(
        "raw",
        ["", "monday", "iso", None, 7, "MONTH_DAY_1"],
    )
    def test_unknown_stored_value_falls_back(self, raw: object) -> None:
        assert coerce_mode(raw) is WeekStartMode.ISO_MONDAY

    @pytest.mark.parametrize("mode", list(WeekStartMode))
    def test_known_value_round_trips(self, mode: WeekStartMode) -> None:
        assert coerce_mode(mode.value) is mode


class TestIsoMonday:
    def test_october_2025_has_five_monday_to_sunday_weeks(self) -> None:
        """The plan's iso_monday criterion for 2025-10-01..2025-10-31."""
        buckets = week_buckets(_days(2025, 10, 31), WeekStartMode.ISO_MONDAY)
        assert _spans(buckets) == [
            ("2025-09-29", "2025-10-05"),
            ("2025-10-06", "2025-10-12"),
            ("2025-10-13", "2025-10-19"),
            ("2025-10-20", "2025-10-26"),
            ("2025-10-27", "2025-11-02"),
        ]
        assert all(bucket.days == 7 for bucket in buckets)
        assert all(bucket.start.weekday() == 0 for bucket in buckets)
        assert all(bucket.end.weekday() == 6 for bucket in buckets)

    @pytest.mark.parametrize(
        ("year", "month", "last", "expected"),
        [
            # 31 days
            (
                2025,
                1,
                31,
                [
                    ("2024-12-30", "2025-01-05"),
                    ("2025-01-06", "2025-01-12"),
                    ("2025-01-13", "2025-01-19"),
                    ("2025-01-20", "2025-01-26"),
                    ("2025-01-27", "2025-02-02"),
                ],
            ),
            # 30 days
            (
                2025,
                4,
                30,
                [
                    ("2025-03-31", "2025-04-06"),
                    ("2025-04-07", "2025-04-13"),
                    ("2025-04-14", "2025-04-20"),
                    ("2025-04-21", "2025-04-27"),
                    ("2025-04-28", "2025-05-04"),
                ],
            ),
            # 29 days (leap February)
            (
                2024,
                2,
                29,
                [
                    ("2024-01-29", "2024-02-04"),
                    ("2024-02-05", "2024-02-11"),
                    ("2024-02-12", "2024-02-18"),
                    ("2024-02-19", "2024-02-25"),
                    ("2024-02-26", "2024-03-03"),
                ],
            ),
            # 28 days (February 2025 runs Sat..Fri, so it touches five weeks)
            (
                2025,
                2,
                28,
                [
                    ("2025-01-27", "2025-02-02"),
                    ("2025-02-03", "2025-02-09"),
                    ("2025-02-10", "2025-02-16"),
                    ("2025-02-17", "2025-02-23"),
                    ("2025-02-24", "2025-03-02"),
                ],
            ),
        ],
    )
    def test_month_lengths(
        self, year: int, month: int, last: int, expected: list[tuple[str, str]]
    ) -> None:
        buckets = week_buckets(_days(year, month, last), WeekStartMode.ISO_MONDAY)
        assert _spans(buckets) == expected
        assert all(bucket.days == 7 for bucket in buckets)

    def test_index_is_the_iso_week_number(self) -> None:
        bucket = week_bucket(datetime.date(2025, 10, 15), WeekStartMode.ISO_MONDAY)
        assert bucket.index == 42

    def test_a_week_crossing_new_year_keeps_one_bucket(self) -> None:
        end_of_year = week_bucket(datetime.date(2024, 12, 31), WeekStartMode.ISO_MONDAY)
        start_of_year = week_bucket(datetime.date(2025, 1, 1), WeekStartMode.ISO_MONDAY)
        assert end_of_year == start_of_year
        assert (str(end_of_year.start), str(end_of_year.end)) == ("2024-12-30", "2025-01-05")


class TestMonthDay1:
    def test_october_2025_weeks_run_in_sevens_from_the_first(self) -> None:
        """The plan's month_day_1 criterion: 01-07 / 08-14 / 15-21 / 22-28 / 29-31."""
        buckets = week_buckets(_days(2025, 10, 31), WeekStartMode.MONTH_DAY_1)
        assert _spans(buckets) == [
            ("2025-10-01", "2025-10-07"),
            ("2025-10-08", "2025-10-14"),
            ("2025-10-15", "2025-10-21"),
            ("2025-10-22", "2025-10-28"),
            ("2025-10-29", "2025-10-31"),
        ]
        assert [bucket.days for bucket in buckets] == [7, 7, 7, 7, 3]
        assert [bucket.index for bucket in buckets] == [1, 2, 3, 4, 5]

    @pytest.mark.parametrize(
        ("year", "month", "last", "expected_days"),
        [
            (2025, 1, 31, [7, 7, 7, 7, 3]),  # 31 days
            (2025, 4, 30, [7, 7, 7, 7, 2]),  # 30 days
            (2024, 2, 29, [7, 7, 7, 7, 1]),  # 29 days — the stub is a single day
            (2025, 2, 28, [7, 7, 7, 7]),  # 28 days — four whole weeks, no stub
        ],
    )
    def test_month_lengths(
        self, year: int, month: int, last: int, expected_days: list[int]
    ) -> None:
        buckets = week_buckets(_days(year, month, last), WeekStartMode.MONTH_DAY_1)
        assert [bucket.days for bucket in buckets] == expected_days
        assert str(buckets[0].start) == f"{year:04d}-{month:02d}-01"
        assert str(buckets[-1].end) == f"{year:04d}-{month:02d}-{last:02d}"

    def test_buckets_never_leave_their_month(self) -> None:
        for day in _days(2025, 4, 30):
            bucket = week_bucket(day, WeekStartMode.MONTH_DAY_1)
            assert bucket.start.month == bucket.end.month == 4
            assert bucket.contains(day)


class TestBucketing:
    def test_only_weeks_with_days_in_them_are_returned(self) -> None:
        sparse = [datetime.date(2025, 10, 2), datetime.date(2025, 10, 30)]
        assert _spans(week_buckets(sparse, WeekStartMode.ISO_MONDAY)) == [
            ("2025-09-29", "2025-10-05"),
            ("2025-10-27", "2025-11-02"),
        ]

    def test_no_days_means_no_buckets(self) -> None:
        assert week_buckets([], WeekStartMode.MONTH_DAY_1) == []

    def test_the_two_modes_disagree_about_the_same_day(self) -> None:
        day = datetime.date(2025, 10, 15)  # a Wednesday
        assert week_bucket(day, WeekStartMode.ISO_MONDAY).start == datetime.date(2025, 10, 13)
        assert week_bucket(day, WeekStartMode.MONTH_DAY_1).start == datetime.date(2025, 10, 15)
