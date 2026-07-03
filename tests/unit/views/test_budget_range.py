"""Unit tests for date_range_for_key() in kaleta.services.budget_service.

All 10 RANGE_OPTIONS keys are tested for correct start/end date boundaries.
"""

from __future__ import annotations

import datetime

import pytest

from kaleta.services.budget_service import date_range_for_key

FIXED_TODAY = datetime.date(2025, 5, 15)


def test_this_month() -> None:
    start, end = date_range_for_key("this_month", today=FIXED_TODAY)
    assert start == datetime.date(2025, 5, 1)
    assert end == datetime.date(2025, 5, 31)


def test_last_month() -> None:
    start, end = date_range_for_key("last_month", today=FIXED_TODAY)
    assert start == datetime.date(2025, 4, 1)
    assert end == datetime.date(2025, 4, 30)


def test_last_month_january_rolls_to_december() -> None:
    start, end = date_range_for_key("last_month", today=datetime.date(2025, 1, 10))
    assert start == datetime.date(2024, 12, 1)
    assert end == datetime.date(2024, 12, 31)


def test_this_quarter_q2() -> None:
    start, end = date_range_for_key("this_quarter", today=FIXED_TODAY)
    assert start == datetime.date(2025, 4, 1)
    assert end == datetime.date(2025, 6, 30)


def test_this_quarter_q1() -> None:
    start, end = date_range_for_key("this_quarter", today=datetime.date(2025, 2, 1))
    assert start == datetime.date(2025, 1, 1)
    assert end == datetime.date(2025, 3, 31)


def test_this_quarter_q3() -> None:
    start, end = date_range_for_key("this_quarter", today=datetime.date(2025, 8, 1))
    assert start == datetime.date(2025, 7, 1)
    assert end == datetime.date(2025, 9, 30)


def test_this_quarter_q4() -> None:
    start, end = date_range_for_key("this_quarter", today=datetime.date(2025, 11, 1))
    assert start == datetime.date(2025, 10, 1)
    assert end == datetime.date(2025, 12, 31)


def test_last_quarter_from_q2() -> None:
    start, end = date_range_for_key("last_quarter", today=FIXED_TODAY)
    assert start == datetime.date(2025, 1, 1)
    assert end == datetime.date(2025, 3, 31)


def test_last_quarter_from_q1_rolls_to_previous_year() -> None:
    start, end = date_range_for_key("last_quarter", today=datetime.date(2025, 2, 1))
    assert start == datetime.date(2024, 10, 1)
    assert end == datetime.date(2024, 12, 31)


def test_this_year() -> None:
    start, end = date_range_for_key("this_year", today=FIXED_TODAY)
    assert start == datetime.date(2025, 1, 1)
    assert end == datetime.date(2025, 12, 31)


def test_last_year() -> None:
    start, end = date_range_for_key("last_year", today=FIXED_TODAY)
    assert start == datetime.date(2024, 1, 1)
    assert end == datetime.date(2024, 12, 31)


def test_last_30_days() -> None:
    start, end = date_range_for_key("last_30_days", today=FIXED_TODAY)
    assert end == FIXED_TODAY
    assert start == FIXED_TODAY - datetime.timedelta(days=30)


def test_last_60_days() -> None:
    start, end = date_range_for_key("last_60_days", today=FIXED_TODAY)
    assert end == FIXED_TODAY
    assert start == FIXED_TODAY - datetime.timedelta(days=60)


def test_last_90_days() -> None:
    start, end = date_range_for_key("last_90_days", today=FIXED_TODAY)
    assert end == FIXED_TODAY
    assert start == FIXED_TODAY - datetime.timedelta(days=90)


def test_last_5_years() -> None:
    start, end = date_range_for_key("last_5_years", today=FIXED_TODAY)
    assert end == FIXED_TODAY
    assert start == datetime.date(2020, 5, 15)


def test_unknown_key_falls_back_to_this_month() -> None:
    start, end = date_range_for_key("completely_invalid_key", today=FIXED_TODAY)
    assert start == datetime.date(2025, 5, 1)
    assert end == datetime.date(2025, 5, 31)


@pytest.mark.parametrize(
    "key",
    [
        "this_month",
        "last_month",
        "this_quarter",
        "last_quarter",
        "this_year",
        "last_year",
        "last_30_days",
        "last_60_days",
        "last_90_days",
        "last_5_years",
    ],
)
def test_end_not_before_start_for_all_keys(key: str) -> None:
    start, end = date_range_for_key(key, today=FIXED_TODAY)
    assert end >= start, f"end < start for key={key!r}: {start} > {end}"
