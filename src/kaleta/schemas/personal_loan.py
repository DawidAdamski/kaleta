from __future__ import annotations

import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from kaleta.models.personal_loan import LoanDirection, LoanStatus

# ── Counterparty ─────────────────────────────────────────────────────────────


class CounterpartyBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)


class CounterpartyCreate(CounterpartyBase):
    pass


class CounterpartyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)


class CounterpartyResponse(CounterpartyBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


# ── Repayments ───────────────────────────────────────────────────────────────


class RepaymentCreate(BaseModel):
    amount: Decimal = Field(..., gt=Decimal("0"), decimal_places=2)
    date: datetime.date
    note: str | None = Field(default=None, max_length=2000)
    # When set, the service creates a matching Transaction on this account
    # so the repayment is reflected in the ledger.
    link_account_id: int | None = None
    link_category_id: int | None = None


class RepaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    loan_id: int
    amount: Decimal
    date: datetime.date
    note: str | None = None
    linked_transaction_id: int | None = None


# ── Loans ────────────────────────────────────────────────────────────────────


class PersonalLoanBase(BaseModel):
    counterparty_id: int
    direction: LoanDirection
    principal: Decimal = Field(..., gt=Decimal("0"), decimal_places=2)
    currency: str = Field(default="PLN", min_length=3, max_length=3)
    opened_at: datetime.date
    due_at: datetime.date | None = None
    notes: str | None = Field(default=None, max_length=4000)


class PersonalLoanCreate(PersonalLoanBase):
    pass


class PersonalLoanUpdate(BaseModel):
    counterparty_id: int | None = None
    direction: LoanDirection | None = None
    principal: Decimal | None = Field(default=None, gt=Decimal("0"), decimal_places=2)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    opened_at: datetime.date | None = None
    due_at: datetime.date | None = None
    notes: str | None = Field(default=None, max_length=4000)
    status: LoanStatus | None = None


class PersonalLoanResponse(PersonalLoanBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: LoanStatus
    settled_at: datetime.datetime | None = None


class PersonalLoanWithRepayments(PersonalLoanResponse):
    counterparty_name: str
    repayments: list[RepaymentResponse] = Field(default_factory=list)
    repaid_total: Decimal
    remaining: Decimal


# ── Totals for the header ────────────────────────────────────────────────────


class LoanTotals(BaseModel):
    they_owe_you: Decimal  # sum of outstanding remaining for OUTGOING loans
    you_owe: Decimal  # sum of outstanding remaining for INCOMING loans
    outstanding_count: int
    settled_count: int


__all__ = [
    "CounterpartyCreate",
    "CounterpartyResponse",
    "CounterpartyUpdate",
    "LoanTotals",
    "PersonalLoanCreate",
    "PersonalLoanResponse",
    "PersonalLoanUpdate",
    "PersonalLoanWithRepayments",
    "RepaymentCreate",
    "RepaymentResponse",
]
