# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Self

from pydantic import BaseModel, ConfigDict, Field

from kaleta.models.account import AccountType

if TYPE_CHECKING:
    from kaleta.models.account import Account

__all__ = [
    "AccountActivityResponse",
    "AccountBase",
    "AccountCreate",
    "AccountResponse",
    "AccountType",
    "AccountUpdate",
]


class AccountBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    type: AccountType = AccountType.CHECKING
    currency: str = Field(default="PLN", min_length=3, max_length=3)
    institution_id: int | None = None


class AccountCreate(AccountBase):
    # The balance today. A new account has no transactions yet, so this is
    # also its opening balance.
    balance: Decimal = Field(default=Decimal("0.00"), decimal_places=2)


class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    type: AccountType | None = None
    # "Set the current balance to this": the service moves the opening
    # balance so that opening + ledger lands here. Transactions are untouched.
    balance: Decimal | None = Field(default=None, decimal_places=2)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    institution_id: int | None = None
    external_account_number: str | None = Field(default=None, max_length=50)


class AccountResponse(AccountBase):
    """An account with its derived current balance.

    ``balance`` is not a column: it is required here, with no default, so an
    ORM row validated without one fails loudly instead of reading as zero.
    Build it with :meth:`from_account`.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    balance: Decimal
    external_account_number: str | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_account(cls, account: Account, balance: Decimal, **extra: Any) -> Self:
        fields = {
            name: getattr(account, name)
            for name in cls.model_fields
            if name != "balance" and name not in extra and hasattr(account, name)
        }
        return cls.model_validate({**fields, "balance": balance, **extra})


class AccountActivityResponse(AccountResponse):
    """Account plus coverage fields for import / accounts UI."""

    newest_transaction_date: date | None = None
    last_import_at: datetime | None = None
    last_import_filename: str | None = None
