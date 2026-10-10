# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import datetime
import enum
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class CurrencyRateCreate(BaseModel):
    date: datetime.date
    from_currency: str = Field(..., min_length=3, max_length=3)
    to_currency: str = Field(..., min_length=3, max_length=3)
    rate: Decimal = Field(..., gt=Decimal("0"))


class RateSource(enum.StrEnum):
    """Where a rate comes from: the family's own table, or the instance's NBP rates."""

    FAMILY = "family"
    NBP = "nbp"


class CurrencyRateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    #: Unique within its ``source`` only: an NBP row's id is ``public.nbp_rates``'.
    id: int
    date: datetime.date
    from_currency: str
    to_currency: str
    rate: Decimal
    created_at: datetime.datetime
    updated_at: datetime.datetime
    #: NBP rows are the instance's; a family can neither edit nor delete them.
    source: RateSource = RateSource.FAMILY
