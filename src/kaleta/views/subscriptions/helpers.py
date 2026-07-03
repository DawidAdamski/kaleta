"""Subscriptions view presentation helpers."""

from __future__ import annotations

import datetime
from decimal import Decimal

from kaleta.i18n import t


def fmt_amount(amount: Decimal) -> str:
    return f"{amount:,.2f}"


def fmt_date(value: datetime.date | None) -> str:
    return value.strftime("%d.%m.%Y") if value else "—"


def cadence_label(days: int) -> str:
    if 27 <= days <= 33:
        return t("subscriptions.detector_cadence_monthly")
    if 350 <= days <= 380:
        return t("subscriptions.detector_cadence_yearly")
    return f"{days}d"


def days_away_label(days: int) -> str:
    if days <= 0:
        return t("subscriptions.renewals_today")
    if days == 1:
        return t("subscriptions.renewals_tomorrow")
    return t("subscriptions.renewals_days_away", days=days)
