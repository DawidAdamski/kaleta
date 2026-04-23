from __future__ import annotations

import datetime
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from kaleta.db.base import Base
from kaleta.models.mixins import TimestampMixin


class CreditCardProfile(TimestampMixin, Base):
    """Credit-card-specific settings attached to an Account of type CREDIT.

    One card per Account. Statement-day and payment-due-day are day-of-month
    (1..28 to avoid end-of-month ambiguity). APR is stored as a percentage
    (e.g. 18.99 for 18.99% p.a.).
    """

    __tablename__ = "credit_card_profiles"
    __table_args__ = (
        UniqueConstraint("account_id", name="uq_credit_card_account"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    credit_limit: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2), nullable=False
    )
    statement_day: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    payment_due_day: Mapped[int] = mapped_column(Integer, nullable=False, default=25)
    min_payment_pct: Mapped[Decimal] = mapped_column(
        Numeric(precision=5, scale=4), nullable=False, default=Decimal("0.02")
    )
    min_payment_floor: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2), nullable=False, default=Decimal("30.00")
    )
    apr: Mapped[Decimal] = mapped_column(
        Numeric(precision=5, scale=2), nullable=False, default=Decimal("0.00")
    )

    def __repr__(self) -> str:
        return (
            f"<CreditCardProfile id={self.id} account_id={self.account_id} "
            f"limit={self.credit_limit}>"
        )


class LoanProfile(TimestampMixin, Base):
    """Amortising loan profile attached to an Account (usually type CREDIT).

    Stored fields are the loan's *contract* values — the current balance lives
    on the Account row and evolves with transactions. ``monthly_payment`` is
    computed from the standard fixed-rate annuity formula at creation time
    but persisted for display stability.
    """

    __tablename__ = "loan_profiles"
    __table_args__ = (UniqueConstraint("account_id", name="uq_loan_account"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    principal: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2), nullable=False
    )
    apr: Mapped[Decimal] = mapped_column(
        Numeric(precision=5, scale=2), nullable=False
    )
    term_months: Mapped[int] = mapped_column(Integer, nullable=False)
    start_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    monthly_payment: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<LoanProfile id={self.id} account_id={self.account_id} "
            f"principal={self.principal} term={self.term_months}>"
        )


__all__ = ["CreditCardProfile", "LoanProfile"]
