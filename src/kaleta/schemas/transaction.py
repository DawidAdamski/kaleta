from __future__ import annotations

import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from kaleta.models.transaction import TransactionType


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
            else:
                if self.category_id is None:
                    raise ValueError(
                        f"{self.type.value.capitalize()} transactions require a category."
                    )
        return self


class TransactionUpdate(BaseModel):
    account_id: int | None = None
    category_id: int | None = None
    amount: Decimal | None = Field(default=None, decimal_places=2)
    type: TransactionType | None = None
    date: datetime.date | None = None
    description: str | None = Field(default=None, max_length=500)
    is_internal_transfer: bool | None = None
    linked_transaction_id: int | None = None
    tag_ids: list[int] | None = None


class TransactionResponse(TransactionBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    splits: list[TransactionSplitResponse] = Field(default_factory=list)
    created_at: datetime.datetime
    updated_at: datetime.datetime
