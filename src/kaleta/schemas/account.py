from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from kaleta.models.account import AccountType


class AccountBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    type: AccountType = AccountType.CHECKING
    balance: Decimal = Field(default=Decimal("0.00"), decimal_places=2)
    institution_id: int | None = None


class AccountCreate(AccountBase):
    pass


class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    type: AccountType | None = None
    balance: Decimal | None = Field(default=None, decimal_places=2)
    institution_id: int | None = None


class AccountResponse(AccountBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
