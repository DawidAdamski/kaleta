# SPDX-License-Identifier: AGPL-3.0-or-later
"""Personal loans view presentation helpers."""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kaleta.schemas.personal_loan import LoanLinkCandidate


def fmt_amount(amount: Decimal) -> str:
    return f"{amount:,.2f}"


def fmt_date(value: datetime.date | None) -> str:
    return value.strftime("%d.%m.%Y") if value else "—"


def notes_preview(notes: str, *, max_chars: int = 80) -> str:
    return notes[:max_chars] + ("…" if len(notes) > max_chars else "")


def link_candidate_label(candidate: LoanLinkCandidate) -> str:
    """One-line picker label: date · amount · description · account."""
    parts = [fmt_date(candidate.date), fmt_amount(candidate.amount)]
    if candidate.description:
        parts.append(candidate.description)
    parts.append(candidate.account_name)
    return " · ".join(parts)
