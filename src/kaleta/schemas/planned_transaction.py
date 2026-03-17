from __future__ import annotations

import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from kaleta.models.planned_transaction import RecurrenceFrequency
from kaleta.models.transaction import TransactionType


class PlannedTransactionCreate(BaseModel):
    name: str = Field(..., max_length=100)
    amount: Decimal = Field(..., gt=0, decimal_places=2)
    type: TransactionType
    account_id: int
    category_id: int | None = None
    description: str | None = Field(default=None, max_length=255)
    frequency: RecurrenceFrequency
    interval: int = Field(default=1, ge=1)
    start_date: datetime.date
    end_date: datetime.date | None = None
    is_active: bool = True


class PlannedTransactionUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    amount: Decimal | None = Field(default=None, gt=0, decimal_places=2)
    type: TransactionType | None = None
    account_id: int | None = None
    category_id: int | None = None
    description: str | None = None
    frequency: RecurrenceFrequency | None = None
    interval: int | None = Field(default=None, ge=1)
    start_date: datetime.date | None = None
    end_date: datetime.date | None = None
    is_active: bool | None = None


class PlannedTransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    amount: Decimal
    type: TransactionType
    account_id: int
    category_id: int | None
    description: str | None
    frequency: RecurrenceFrequency
    interval: int
    start_date: datetime.date
    end_date: datetime.date | None
    is_active: bool
    created_at: datetime.datetime
    updated_at: datetime.datetime
