# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for the remembered quick-entry context.

Covers: KAL-QIK-002
"""

from __future__ import annotations

import datetime

from kaleta.views.transactions.quick_entry import QuickEntryContext

TODAY = datetime.date(2026, 7, 5)


def test_date_is_kept_on_the_day_it_was_saved() -> None:
    ctx = QuickEntryContext(account_id=1, date=datetime.date(2026, 7, 1), saved_on=TODAY)
    assert ctx.date_for(TODAY) == datetime.date(2026, 7, 1)


def test_date_falls_back_to_today_on_a_later_day() -> None:
    ctx = QuickEntryContext(
        account_id=1, date=datetime.date(2026, 7, 1), saved_on=datetime.date(2026, 7, 4)
    )
    assert ctx.date_for(TODAY) == TODAY


def test_nothing_remembered_means_today_and_fallback_account() -> None:
    ctx = QuickEntryContext.from_raw(None)
    assert ctx.date_for(TODAY) == TODAY
    assert ctx.account_for({1, 2}, fallback=2) == 2


def test_remembered_account_wins_while_it_exists() -> None:
    ctx = QuickEntryContext(account_id=1, date=None, saved_on=None)
    assert ctx.account_for({1, 2}, fallback=2) == 1


def test_deleted_account_falls_back() -> None:
    ctx = QuickEntryContext(account_id=9, date=None, saved_on=None)
    assert ctx.account_for({1, 2}, fallback=2) == 2


def test_round_trip_through_storage_shape() -> None:
    ctx = QuickEntryContext(account_id=3, date=datetime.date(2026, 7, 5), saved_on=TODAY)
    assert QuickEntryContext.from_raw(ctx.to_raw()) == ctx


def test_malformed_storage_is_ignored() -> None:
    ctx = QuickEntryContext.from_raw({"account_id": "x", "date": "not-a-date", "saved_on": 5})
    assert ctx == QuickEntryContext(account_id=None, date=None, saved_on=None)
