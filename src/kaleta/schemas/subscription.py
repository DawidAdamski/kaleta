from __future__ import annotations

import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from kaleta.models.subscription import SubscriptionStatus


class SubscriptionBase(BaseModel):
    """Shared editable fields for a subscription."""

    name: str = Field(..., min_length=1, max_length=200)
    amount: Decimal = Field(..., gt=Decimal("0"), decimal_places=2)
    cadence_days: int = Field(default=30, ge=1, le=400)
    payee_id: int | None = None
    category_id: int | None = None
    first_seen_at: datetime.date | None = None
    next_expected_at: datetime.date | None = None
    url: str | None = Field(default=None, max_length=500)
    auto_renew: bool = True
    notes: str | None = Field(default=None, max_length=4000)


class SubscriptionCreate(SubscriptionBase):
    pass


class SubscriptionUpdate(BaseModel):
    """PATCH semantics — all fields optional."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    amount: Decimal | None = Field(default=None, gt=Decimal("0"), decimal_places=2)
    cadence_days: int | None = Field(default=None, ge=1, le=400)
    payee_id: int | None = None
    category_id: int | None = None
    first_seen_at: datetime.date | None = None
    next_expected_at: datetime.date | None = None
    url: str | None = Field(default=None, max_length=500)
    auto_renew: bool | None = None
    notes: str | None = Field(default=None, max_length=4000)
    status: SubscriptionStatus | None = None
    muted_until: datetime.date | None = None
    cancelled_at: datetime.date | None = None


class SubscriptionResponse(SubscriptionBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: SubscriptionStatus
    muted_until: datetime.date | None = None
    cancelled_at: datetime.date | None = None


class DetectorCandidate(BaseModel):
    """A recurring-charge group surfaced by the detector."""

    payee_id: int | None
    payee_name: str
    amount: Decimal
    cadence_days: int
    occurrences: int
    first_seen_at: datetime.date
    last_seen_at: datetime.date
    next_expected_at: datetime.date


class RenewalRow(BaseModel):
    """A single upcoming-charge row."""

    subscription_id: int
    name: str
    amount: Decimal
    expected_at: datetime.date
    days_away: int


class SubscriptionTotals(BaseModel):
    active_count: int
    monthly_total: Decimal
    yearly_total: Decimal
