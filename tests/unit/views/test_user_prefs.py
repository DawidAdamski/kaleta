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


def test_ledger_page_sizes_match_the_in_page_selector() -> None:
    """The Settings default and the ledger's own selector offer the same sizes.

    They are defined in two places (settings constants and the table
    component); this guards them against drifting apart.
    """
    from kaleta.views.components.transaction_table import DEFAULT_PAGE_SIZE, PAGE_SIZES
    from kaleta.views.settings.constants import (
        DEFAULT_TRANSACTIONS_PAGE_SIZE,
        TRANSACTIONS_PAGE_SIZE_CHOICES,
    )

    assert list(TRANSACTIONS_PAGE_SIZE_CHOICES) == PAGE_SIZES
    assert DEFAULT_PAGE_SIZE == DEFAULT_TRANSACTIONS_PAGE_SIZE
    assert DEFAULT_TRANSACTIONS_PAGE_SIZE in TRANSACTIONS_PAGE_SIZE_CHOICES


def test_ledger_grouping_default_is_an_offered_grouping() -> None:
    from kaleta.views.settings.constants import (
        DEFAULT_TRANSACTIONS_GROUPING,
        TRANSACTIONS_GROUPING_CHOICES,
    )

    assert DEFAULT_TRANSACTIONS_GROUPING in TRANSACTIONS_GROUPING_CHOICES
