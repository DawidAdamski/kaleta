"""Unit tests for _date_range() helper in kaleta.views.budgets.

All 10 RANGE_OPTIONS keys are tested for correct start/end date boundaries.
Tests use a fixed reference date injected via monkeypatching so results are
deterministic regardless of when the suite runs.
"""

from __future__ import annotations

import datetime

import pytest

# We import the private helper directly — it is a pure function with no DB access.
from kaleta.views.budgets import _date_range

# Fixed reference "today" used by every test below.
FIXED_TODAY = datetime.date(2025, 5, 15)


def _patch_today(monkeypatch: pytest.MonkeyPatch, fake_today: datetime.date) -> None:
    """Patch datetime.date.today() inside the budgets module."""

    class _FakeDate(datetime.date):
        @classmethod
        def today(cls) -> datetime.date:  # type: ignore[override]
            return fake_today

    monkeypatch.setattr("kaleta.views.budgets.datetime.date", _FakeDate)


# ── this_month ─────────────────────────────────────────────────────────────────


def test_this_month(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_today(monkeypatch, FIXED_TODAY)
    start, end = _date_range("this_month")
    assert start == datetime.date(2025, 5, 1)
    assert end == datetime.date(2025, 5, 31)


# ── last_month ─────────────────────────────────────────────────────────────────


def test_last_month(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_today(monkeypatch, FIXED_TODAY)
    start, end = _date_range("last_month")
    assert start == datetime.date(2025, 4, 1)
    assert end == datetime.date(2025, 4, 30)


def test_last_month_january_rolls_to_december(monkeypatch: pytest.MonkeyPatch) -> None:
    """When today is in January, last month must cross the year boundary."""
    _patch_today(monkeypatch, datetime.date(2025, 1, 10))
    start, end = _date_range("last_month")
    assert start == datetime.date(2024, 12, 1)
    assert end == datetime.date(2024, 12, 31)


# ── this_quarter ───────────────────────────────────────────────────────────────


def test_this_quarter_q2(monkeypatch: pytest.MonkeyPatch) -> None:
    """May is in Q2 (Apr–Jun)."""
    _patch_today(monkeypatch, FIXED_TODAY)
    start, end = _date_range("this_quarter")
    assert start == datetime.date(2025, 4, 1)
    assert end == datetime.date(2025, 6, 30)


def test_this_quarter_q1(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_today(monkeypatch, datetime.date(2025, 2, 1))
    start, end = _date_range("this_quarter")
    assert start == datetime.date(2025, 1, 1)
    assert end == datetime.date(2025, 3, 31)


def test_this_quarter_q3(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_today(monkeypatch, datetime.date(2025, 8, 1))
    start, end = _date_range("this_quarter")
    assert start == datetime.date(2025, 7, 1)
    assert end == datetime.date(2025, 9, 30)


def test_this_quarter_q4(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_today(monkeypatch, datetime.date(2025, 11, 1))
    start, end = _date_range("this_quarter")
    assert start == datetime.date(2025, 10, 1)
    assert end == datetime.date(2025, 12, 31)


# ── last_quarter ───────────────────────────────────────────────────────────────


def test_last_quarter_from_q2(monkeypatch: pytest.MonkeyPatch) -> None:
    """Today in Q2 → last quarter is Q1."""
    _patch_today(monkeypatch, FIXED_TODAY)
    start, end = _date_range("last_quarter")
    assert start == datetime.date(2025, 1, 1)
    assert end == datetime.date(2025, 3, 31)


def test_last_quarter_from_q1_rolls_to_previous_year(monkeypatch: pytest.MonkeyPatch) -> None:
    """Today in Q1 → last quarter is Q4 of the previous year."""
    _patch_today(monkeypatch, datetime.date(2025, 2, 1))
    start, end = _date_range("last_quarter")
    assert start == datetime.date(2024, 10, 1)
    assert end == datetime.date(2024, 12, 31)


# ── this_year ─────────────────────────────────────────────────────────────────


def test_this_year(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_today(monkeypatch, FIXED_TODAY)
    start, end = _date_range("this_year")
    assert start == datetime.date(2025, 1, 1)
    assert end == datetime.date(2025, 12, 31)


# ── last_year ─────────────────────────────────────────────────────────────────


def test_last_year(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_today(monkeypatch, FIXED_TODAY)
    start, end = _date_range("last_year")
    assert start == datetime.date(2024, 1, 1)
    assert end == datetime.date(2024, 12, 31)


# ── last_30_days ───────────────────────────────────────────────────────────────


def test_last_30_days(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_today(monkeypatch, FIXED_TODAY)
    start, end = _date_range("last_30_days")
    assert end == FIXED_TODAY
    assert start == FIXED_TODAY - datetime.timedelta(days=30)


# ── last_60_days ───────────────────────────────────────────────────────────────


def test_last_60_days(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_today(monkeypatch, FIXED_TODAY)
    start, end = _date_range("last_60_days")
    assert end == FIXED_TODAY
    assert start == FIXED_TODAY - datetime.timedelta(days=60)


# ── last_90_days ───────────────────────────────────────────────────────────────


def test_last_90_days(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_today(monkeypatch, FIXED_TODAY)
    start, end = _date_range("last_90_days")
    assert end == FIXED_TODAY
    assert start == FIXED_TODAY - datetime.timedelta(days=90)


# ── last_5_years ───────────────────────────────────────────────────────────────


def test_last_5_years(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_today(monkeypatch, FIXED_TODAY)
    start, end = _date_range("last_5_years")
    assert end == FIXED_TODAY
    assert start == datetime.date(2020, 5, 15)


# ── unknown key falls back to this_month ──────────────────────────────────────


def test_unknown_key_falls_back_to_this_month(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_today(monkeypatch, FIXED_TODAY)
    start, end = _date_range("completely_invalid_key")
    assert start == datetime.date(2025, 5, 1)
    assert end == datetime.date(2025, 5, 31)


# ── end >= start for all known keys ───────────────────────────────────────────


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
def test_end_not_before_start_for_all_keys(monkeypatch: pytest.MonkeyPatch, key: str) -> None:
    _patch_today(monkeypatch, FIXED_TODAY)
    start, end = _date_range(key)
    assert end >= start, f"end < start for key={key!r}: {start} > {end}"
