# SPDX-License-Identifier: AGPL-3.0-or-later
"""Personal loans view presentation helpers."""

from __future__ import annotations

import datetime
from decimal import Decimal


def fmt_amount(amount: Decimal) -> str:
    return f"{amount:,.2f}"


def fmt_date(value: datetime.date | None) -> str:
    return value.strftime("%d.%m.%Y") if value else "—"


def notes_preview(notes: str, *, max_chars: int = 80) -> str:
    return notes[:max_chars] + ("…" if len(notes) > max_chars else "")
