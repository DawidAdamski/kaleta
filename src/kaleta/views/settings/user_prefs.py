# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read persisted user preferences from ``app.storage.user`` with defaults."""

from __future__ import annotations

import datetime
from decimal import Decimal

from nicegui import app

from kaleta.views.settings.constants import (
    DEFAULT_BUDGET_MONTH_START_DAY,
    DEFAULT_EVENT_RETENTION_DAYS,
    DEFAULT_EVENTS_ENABLED,
    DEFAULT_IMPORT_SKIP_DUPLICATES,
    DEFAULT_NUMBER_FORMAT,
    DEFAULT_PAYEE_DEDUPE_MAX_DISTANCE,
    DEFAULT_TRANSFER_AMOUNT_TOLERANCE,
    DEFAULT_TRANSFER_PAIRING_DAYS,
)

__all__ = [
    "budget_period_for",
    "budget_period_for_date",
    "get_budget_month_start_day",
    "get_default_account_id",
    "get_event_retention_days",
    "get_events_enabled",
    "get_import_skip_duplicates_default",
    "get_number_format",
    "get_payee_dedupe_max_distance",
    "get_transfer_amount_tolerance",
    "get_transfer_pairing_days",
]


def get_number_format() -> str:
    raw = app.storage.user.get("number_format", DEFAULT_NUMBER_FORMAT)
    return str(raw) if raw in {"eu", "us"} else DEFAULT_NUMBER_FORMAT


def get_budget_month_start_day() -> int:
    raw = app.storage.user.get("budget_month_start_day", DEFAULT_BUDGET_MONTH_START_DAY)
    try:
        day = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_BUDGET_MONTH_START_DAY
    return max(1, min(28, day))


def budget_period_for(on_date: datetime.date | None = None) -> tuple[int, int]:
    """Return ``(year, month)`` for the budget period containing ``on_date``."""
    day = on_date or datetime.date.today()
    return budget_period_for_date(day, start_day=get_budget_month_start_day())


def budget_period_for_date(on_date: datetime.date, *, start_day: int) -> tuple[int, int]:
    """Pure helper — budget calendar month for ``on_date`` given a start day."""
    clamped = max(1, min(28, start_day))
    if clamped <= 1 or on_date.day >= clamped:
        return on_date.year, on_date.month
    if on_date.month == 1:
        return on_date.year - 1, 12
    return on_date.year, on_date.month - 1


def get_default_account_id() -> int | None:
    raw = app.storage.user.get("default_account_id")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def get_transfer_pairing_days() -> int:
    raw = app.storage.user.get("transfer_pairing_days", DEFAULT_TRANSFER_PAIRING_DAYS)
    try:
        return max(0, min(30, int(raw)))
    except (TypeError, ValueError):
        return DEFAULT_TRANSFER_PAIRING_DAYS


def get_transfer_amount_tolerance() -> Decimal:
    raw = app.storage.user.get("transfer_amount_tolerance", DEFAULT_TRANSFER_AMOUNT_TOLERANCE)
    try:
        value = Decimal(str(raw))
    except Exception:
        return DEFAULT_TRANSFER_AMOUNT_TOLERANCE
    return max(Decimal("0"), min(Decimal("100"), value))


def get_payee_dedupe_max_distance() -> int:
    raw = app.storage.user.get("payee_dedupe_max_distance", DEFAULT_PAYEE_DEDUPE_MAX_DISTANCE)
    try:
        return max(1, min(5, int(raw)))
    except (TypeError, ValueError):
        return DEFAULT_PAYEE_DEDUPE_MAX_DISTANCE


def get_import_skip_duplicates_default() -> bool:
    raw = app.storage.user.get("import_skip_duplicates_default", DEFAULT_IMPORT_SKIP_DUPLICATES)
    return bool(raw)


def get_events_enabled() -> bool:
    raw = app.storage.user.get("events_enabled", DEFAULT_EVENTS_ENABLED)
    return bool(raw)


def get_event_retention_days() -> int:
    raw = app.storage.user.get("event_retention_days", DEFAULT_EVENT_RETENTION_DAYS)
    try:
        return max(1, min(90, int(raw)))
    except (TypeError, ValueError):
        return DEFAULT_EVENT_RETENTION_DAYS
