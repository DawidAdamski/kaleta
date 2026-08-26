# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for budget period helpers."""

from __future__ import annotations

import datetime

from kaleta.views.settings.user_prefs import budget_period_for_date


def test_budget_period_calendar_month_when_start_day_is_one() -> None:
    d = datetime.date(2026, 3, 15)
    assert budget_period_for_date(d, start_day=1) == (2026, 3)


def test_budget_period_rolls_back_before_start_day() -> None:
    d = datetime.date(2026, 3, 10)
    assert budget_period_for_date(d, start_day=15) == (2026, 2)


def test_budget_period_january_rolls_to_previous_year() -> None:
    d = datetime.date(2026, 1, 5)
    assert budget_period_for_date(d, start_day=10) == (2025, 12)


def test_budget_period_on_start_day_uses_current_month() -> None:
    d = datetime.date(2026, 4, 15)
    assert budget_period_for_date(d, start_day=15) == (2026, 4)
