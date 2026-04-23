from __future__ import annotations

import datetime
import enum
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

# ── Credit-card profile ──────────────────────────────────────────────────────


class CreditCardProfileBase(BaseModel):
    credit_limit: Decimal = Field(..., gt=Decimal("0"), decimal_places=2)
    statement_day: int = Field(default=1, ge=1, le=28)
    payment_due_day: int = Field(default=25, ge=1, le=28)
    min_payment_pct: Decimal = Field(
        default=Decimal("0.02"), ge=Decimal("0"), le=Decimal("1"), decimal_places=4
    )
    min_payment_floor: Decimal = Field(
        default=Decimal("30.00"), ge=Decimal("0"), decimal_places=2
    )
    apr: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0"), decimal_places=2)


class CreditCardProfileCreate(CreditCardProfileBase):
    account_id: int


class CreditCardProfileUpdate(BaseModel):
    credit_limit: Decimal | None = Field(
        default=None, gt=Decimal("0"), decimal_places=2
    )
    statement_day: int | None = Field(default=None, ge=1, le=28)
    payment_due_day: int | None = Field(default=None, ge=1, le=28)
    min_payment_pct: Decimal | None = Field(
        default=None, ge=Decimal("0"), le=Decimal("1"), decimal_places=4
    )
    min_payment_floor: Decimal | None = Field(
        default=None, ge=Decimal("0"), decimal_places=2
    )
    apr: Decimal | None = Field(default=None, ge=Decimal("0"), decimal_places=2)


class CreditCardProfileResponse(CreditCardProfileBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    account_id: int


# ── Loan profile ─────────────────────────────────────────────────────────────


class LoanProfileBase(BaseModel):
    principal: Decimal = Field(..., gt=Decimal("0"), decimal_places=2)
    apr: Decimal = Field(..., ge=Decimal("0"), decimal_places=2)
    term_months: int = Field(..., ge=1, le=600)
    start_date: datetime.date


class LoanProfileCreate(LoanProfileBase):
    account_id: int


class LoanProfileUpdate(BaseModel):
    principal: Decimal | None = Field(default=None, gt=Decimal("0"), decimal_places=2)
    apr: Decimal | None = Field(default=None, ge=Decimal("0"), decimal_places=2)
    term_months: int | None = Field(default=None, ge=1, le=600)
    start_date: datetime.date | None = None


class LoanProfileResponse(LoanProfileBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    account_id: int
    monthly_payment: Decimal


# ── Derived types for the view ───────────────────────────────────────────────


class CreditStatus(enum.StrEnum):
    ON_TIME = "on_time"
    GRACE = "grace"
    OVERDUE = "overdue"


class CardView(BaseModel):
    """Everything the Credit → Cards tab needs for one row."""

    account_id: int
    account_name: str
    currency: str
    current_balance: Decimal
    credit_limit: Decimal
    utilization_pct: Decimal  # 0..1+
    min_payment: Decimal
    next_due_at: datetime.date
    status: CreditStatus


class AmortisationRow(BaseModel):
    month: int
    date: datetime.date
    payment: Decimal
    principal_paid: Decimal
    interest_paid: Decimal
    remaining_principal: Decimal


class LoanView(BaseModel):
    """Everything the Credit → Loans tab needs for one row."""

    account_id: int
    account_name: str
    currency: str
    principal: Decimal
    apr: Decimal
    term_months: int
    monthly_payment: Decimal
    start_date: datetime.date
    months_elapsed: int
    remaining_balance: Decimal
    next_due_at: datetime.date
    status: CreditStatus


__all__ = [
    "AmortisationRow",
    "CardView",
    "CreditCardProfileCreate",
    "CreditCardProfileResponse",
    "CreditCardProfileUpdate",
    "CreditStatus",
    "LoanProfileCreate",
    "LoanProfileResponse",
    "LoanProfileUpdate",
    "LoanView",
]
