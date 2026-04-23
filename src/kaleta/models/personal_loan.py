from __future__ import annotations

import datetime
import enum
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kaleta.db.base import Base
from kaleta.models.mixins import TimestampMixin


class LoanDirection(enum.StrEnum):
    """Who owes whom.

    ``OUTGOING``  — the user lent money; the counterparty owes them.
    ``INCOMING``  — the user borrowed money; they owe the counterparty.
    """

    OUTGOING = "outgoing"
    INCOMING = "incoming"


class LoanStatus(enum.StrEnum):
    OUTSTANDING = "outstanding"
    SETTLED = "settled"


class Counterparty(TimestampMixin, Base):
    """A person on the other end of a personal loan. Reused across loans."""

    __tablename__ = "counterparties"
    __table_args__ = (UniqueConstraint("name", name="uq_counterparty_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    loans: Mapped[list[PersonalLoan]] = relationship(
        "PersonalLoan", back_populates="counterparty", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Counterparty id={self.id} name={self.name!r}>"


class PersonalLoan(TimestampMixin, Base):
    """Money lent to or borrowed from a counterparty outside the bank ledger."""

    __tablename__ = "personal_loans"

    id: Mapped[int] = mapped_column(primary_key=True)
    counterparty_id: Mapped[int] = mapped_column(
        ForeignKey("counterparties.id", ondelete="CASCADE"), nullable=False
    )
    direction: Mapped[LoanDirection] = mapped_column(
        SAEnum(LoanDirection, native_enum=False), nullable=False
    )
    principal: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2), nullable=False
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="PLN")
    opened_at: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    due_at: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[LoanStatus] = mapped_column(
        SAEnum(LoanStatus, native_enum=False),
        nullable=False,
        default=LoanStatus.OUTSTANDING,
    )
    settled_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)

    counterparty: Mapped[Counterparty] = relationship(
        "Counterparty", back_populates="loans"
    )
    repayments: Mapped[list[PersonalLoanRepayment]] = relationship(
        "PersonalLoanRepayment",
        back_populates="loan",
        cascade="all, delete-orphan",
        order_by="PersonalLoanRepayment.date",
    )

    def __repr__(self) -> str:
        return (
            f"<PersonalLoan id={self.id} direction={self.direction} "
            f"principal={self.principal} status={self.status}>"
        )


class PersonalLoanRepayment(TimestampMixin, Base):
    """A partial or full repayment against a PersonalLoan."""

    __tablename__ = "personal_loan_repayments"

    id: Mapped[int] = mapped_column(primary_key=True)
    loan_id: Mapped[int] = mapped_column(
        ForeignKey("personal_loans.id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2), nullable=False
    )
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Optional link to a real Transaction — filled when the user opted to
    # mirror this repayment as a transaction on a bank account.
    linked_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True
    )

    loan: Mapped[PersonalLoan] = relationship("PersonalLoan", back_populates="repayments")

    def __repr__(self) -> str:
        return (
            f"<PersonalLoanRepayment id={self.id} loan_id={self.loan_id} "
            f"amount={self.amount} date={self.date}>"
        )


# Re-export for cleaner import in services/schemas.
__all__ = [
    "Counterparty",
    "LoanDirection",
    "LoanStatus",
    "PersonalLoan",
    "PersonalLoanRepayment",
]
