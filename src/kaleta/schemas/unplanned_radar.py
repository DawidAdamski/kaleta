# SPDX-License-Identifier: AGPL-3.0-or-later
"""Schemas for the unplanned-expenses radar (irregular recurring costs)."""

from __future__ import annotations

import datetime
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel

from kaleta.models.planned_transaction import RecurrenceFrequency

_CENTS = Decimal("0.01")

__all__ = [
    "RadarCandidate",
    "RadarSummary",
    "RadarPlannedRow",
]


class RadarCandidate(BaseModel):
    """An irregular cost that repeated often enough to look like a pattern.

    Unlike a subscription candidate this is low-frequency: consecutive
    occurrences sit at least two months apart, and the amount is allowed to
    drift (car service, dentist, school fees).
    """

    payee_id: int | None
    source_name: str
    typical_amount: Decimal
    occurrences: int
    first_seen_at: datetime.date
    last_seen_at: datetime.date
    average_gap_days: int
    next_expected_at: datetime.date
    frequency: RecurrenceFrequency
    interval: int
    yearly_estimate: Decimal
    account_id: int
    category_id: int | None
    occurrence_dates: list[datetime.date]
    transaction_ids: list[int]


class RadarSummary(BaseModel):
    """Roll-up of every candidate — the irregular-fund suggestion line."""

    candidate_count: int
    yearly_total: Decimal
    monthly_equivalent: Decimal

    @classmethod
    def from_candidates(cls, candidates: list[RadarCandidate]) -> RadarSummary:
        """Total what the radar found, as a year and as a month of saving."""
        yearly = sum((c.yearly_estimate for c in candidates), Decimal("0"))
        yearly = yearly.quantize(_CENTS, rounding=ROUND_HALF_UP)
        return cls(
            candidate_count=len(candidates),
            yearly_total=yearly,
            monthly_equivalent=(yearly / Decimal(12)).quantize(_CENTS, rounding=ROUND_HALF_UP),
        )


class RadarPlannedRow(BaseModel):
    """A planned transaction that carries charges predating its start date.

    Conversion from the radar is what normally produces those links, but
    nothing records who made them — a charge linked by hand appears here too.
    """

    planned_id: int
    name: str
    amount: Decimal
    frequency: RecurrenceFrequency
    interval: int
    start_date: datetime.date
    linked_count: int
    linked_dates: list[datetime.date]
