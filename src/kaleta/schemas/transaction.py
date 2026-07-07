# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from kaleta.models.transaction import TransactionType

__all__ = [
    "TransactionSplitCreate",
    "TransactionSplitResponse",
    "TransactionBase",
    "TransactionCreate",
    "TransactionUpdate",
    "TransactionResponse",
    "TransactionType",
]


class TransactionSplitCreate(BaseModel):
    category_id: int | None = None
    amount: Decimal = Field(..., decimal_places=2, gt=Decimal("0"))
    note: str = Field(default="", max_length=255)


class TransactionSplitResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    transaction_id: int
    category_id: int | None
    amount: Decimal
    note: str


class TransactionBase(BaseModel):
    account_id: int
    category_id: int | None = None
    payee_id: int | None = None
    amount: Decimal = Field(..., decimal_places=2)
    # Exchange rate for cross-currency transfers: dest_currency per 1 src_currency unit
    exchange_rate: Decimal | None = None
    type: TransactionType
    date: datetime.date
    description: str = Field(default="", max_length=500)
    is_internal_transfer: bool = False
    is_split: bool = False
    linked_transaction_id: int | None = None


class TransactionCreate(TransactionBase):
    splits: list[TransactionSplitCreate] = Field(default_factory=list)
    tag_ids: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_rules(self) -> TransactionCreate:
        if self.is_internal_transfer and self.type != TransactionType.TRANSFER:
            raise ValueError("Internal transfers must have type='transfer'.")
        if self.type in (TransactionType.INCOME, TransactionType.EXPENSE):
            if self.is_split:
                if not self.splits:
                    raise ValueError("Split transactions must have at least one split.")
                if self.category_id is not None:
                    raise ValueError("Split transactions must not set a top-level category.")
                split_total = sum((s.amount for s in self.splits), start=Decimal("0"))
                if split_total != self.amount:
                    remaining = self.amount - split_total
                    raise ValueError(
                        f"Split amounts must sum to {self.amount}; {remaining:+.2f} remaining."
                    )
            else:
                if self.category_id is None:
                    raise ValueError(
                        f"{self.type.value.capitalize()} transactions require a category."
                    )
        return self


class TransactionUpdate(BaseModel):
    account_id: int | None = None
    category_id: int | None = None
    payee_id: int | None = None
    amount: Decimal | None = Field(default=None, decimal_places=2)
    type: TransactionType | None = None
    date: datetime.date | None = None
    description: str | None = Field(default=None, max_length=500)
    is_internal_transfer: bool | None = None
    is_split: bool | None = None
    linked_transaction_id: int | None = None
    tag_ids: list[int] | None = None
    splits: list[TransactionSplitCreate] | None = None


class TransactionResponse(TransactionBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    payee_name: str | None = None
    splits: list[TransactionSplitResponse] = Field(default_factory=list)
    created_at: datetime.datetime
    updated_at: datetime.datetime

    @model_validator(mode="wrap")
    @classmethod
    def _set_payee_name(cls, value: Any, handler: Any) -> TransactionResponse:
        obj = cast(TransactionResponse, handler(value))
        if hasattr(value, "payee") and value.payee is not None:
            obj.payee_name = value.payee.name
        return obj
