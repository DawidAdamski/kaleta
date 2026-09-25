# SPDX-License-Identifier: AGPL-3.0-or-later
"""Remembered context for quick transaction entry (account and date).

The add dialog preselects the account and date of the last save, so a run of
receipts does not have to re-pick them. The date is only carried over on the
calendar day it was saved: a context left over from yesterday falls back to
today, because an entry session rarely spans midnight and a stale date is an
easy mistake to miss.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any

from nicegui import app

STORAGE_KEY = "quick_entry_context"


@dataclass(frozen=True)
class QuickEntryContext:
    account_id: int | None
    date: datetime.date | None
    saved_on: datetime.date | None

    def date_for(self, today: datetime.date) -> datetime.date:
        """The date to preselect: the remembered one on the day it was saved, else today."""
        if self.date is not None and self.saved_on == today:
            return self.date
        return today

    def account_for(self, account_ids: set[int], fallback: int | None) -> int | None:
        """The account to preselect: the remembered one while it still exists."""
        if self.account_id is not None and self.account_id in account_ids:
            return self.account_id
        return fallback

    @classmethod
    def from_raw(cls, raw: Any) -> QuickEntryContext:
        """Parse the stored dict, treating anything malformed as "nothing remembered"."""
        if not isinstance(raw, dict):
            return cls(account_id=None, date=None, saved_on=None)
        return cls(
            account_id=_parse_int(raw.get("account_id")),
            date=_parse_date(raw.get("date")),
            saved_on=_parse_date(raw.get("saved_on")),
        )

    def to_raw(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id,
            "date": self.date.isoformat() if self.date else None,
            "saved_on": self.saved_on.isoformat() if self.saved_on else None,
        }


class QuickEntryMemory:
    """Reads and writes the quick-entry context in per-user storage."""

    @staticmethod
    def load() -> QuickEntryContext:
        return QuickEntryContext.from_raw(app.storage.user.get(STORAGE_KEY))

    @staticmethod
    def remember(account_id: int, date: datetime.date) -> None:
        context = QuickEntryContext(
            account_id=account_id, date=date, saved_on=datetime.date.today()
        )
        app.storage.user[STORAGE_KEY] = context.to_raw()


def _parse_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_date(value: Any) -> datetime.date | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        return None
