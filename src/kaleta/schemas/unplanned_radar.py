# SPDX-License-Identifier: AGPL-3.0-or-later
"""Schemas for the unplanned-expenses radar (irregular recurring costs)."""

from __future__ import annotations

import datetime
from decimal import Decimal

from pydantic import BaseModel

from kaleta.models.planned_transaction import RecurrenceFrequency

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


class RadarPlannedRow(BaseModel):
    """A planned transaction the radar created, with its history link count."""

    planned_id: int
    name: str
    amount: Decimal
    frequency: RecurrenceFrequency
    interval: int
    start_date: datetime.date
    linked_count: int
    linked_dates: list[datetime.date]
