# SPDX-License-Identifier: AGPL-3.0-or-later
import enum
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Numeric,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kaleta.db.base import Base
from kaleta.db.types import EncryptedText
from kaleta.models.mixins import TimestampMixin, UserOwnedMixin
from kaleta.models.tag import transaction_tags


class TransactionType(str, enum.Enum):  # noqa: UP042
    INCOME = "income"
    EXPENSE = "expense"
    TRANSFER = "transfer"


class TransferDirection(enum.StrEnum):
    """Which way the money moved on one leg of a transfer.

    ``amount`` is unsigned on every row, and ``type`` gives the sign of an
    income or an expense. A transfer leg needs this to say whether the money
    left its account (``out``) or arrived on it (``in``), and account
    balances are derived from it (see ``AccountService.balances``).
    """

    OUT = "out"
    IN = "in"


class Transaction(TimestampMixin, UserOwnedMixin, Base):
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint(
            "planned_transaction_id",
            "date",
            name="uq_transactions_planned_occurrence",
        ),
        # A transfer leg always knows its direction, and nothing else has one.
        # Enums are stored by member name (no ``values_callable``).
        CheckConstraint(
            "(type = 'TRANSFER') = (transfer_direction IS NOT NULL)",
            name="ck_transactions_transfer_direction",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    payee_id: Mapped[int | None] = mapped_column(
        ForeignKey("payees.id", ondelete="SET NULL"), nullable=True
    )
    # Self-referential FK for linking paired internal transfer legs
    linked_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id"), nullable=True
    )
    # When set, this row is the posted ledger entry for one planned occurrence.
    planned_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("planned_transactions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    amount: Mapped[Decimal] = mapped_column(Numeric(precision=15, scale=2), nullable=False)
    # For cross-currency transfers: how many dest-currency units per 1 src-currency unit
    exchange_rate: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=15, scale=6), nullable=True
    )
    type: Mapped[TransactionType] = mapped_column(
        SAEnum(TransactionType, native_enum=False), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(
        EncryptedText("transactions.description"), nullable=False, default=""
    )
    # Long-form user note kept apart from the bank-imported ``description``.
    # Blank input is normalised to NULL by the schema — one empty representation only.
    notes: Mapped[str | None] = mapped_column(EncryptedText("transactions.notes"), nullable=True)
    transfer_direction: Mapped[TransferDirection | None] = mapped_column(
        SAEnum(TransferDirection, native_enum=False), nullable=True
    )
    is_internal_transfer: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_split: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    account: Mapped["Account"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Account", back_populates="transactions"
    )
    category: Mapped["Category | None"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Category", back_populates="transactions"
    )
    payee: Mapped["Payee | None"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Payee", back_populates="transactions"
    )
    linked_transaction: Mapped["Transaction | None"] = relationship(
        "Transaction", remote_side="Transaction.id", foreign_keys=[linked_transaction_id]
    )
    planned_transaction: Mapped["PlannedTransaction | None"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "PlannedTransaction", foreign_keys=[planned_transaction_id]
    )
    splits: Mapped[list["TransactionSplit"]] = relationship(
        "TransactionSplit", back_populates="transaction", cascade="all, delete-orphan"
    )
    tags: Mapped[list["Tag"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Tag", secondary=transaction_tags, back_populates="transactions"
    )

    def __repr__(self) -> str:
        return f"<Transaction id={self.id} amount={self.amount} date={self.date}>"


class TransactionSplit(Base):
    __tablename__ = "transaction_splits"
    __table_args__ = (Index("ix_transaction_splits_transaction_id", "transaction_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False
    )
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(precision=15, scale=2), nullable=False)
    note: Mapped[str] = mapped_column(
        EncryptedText("transaction_splits.note"), nullable=False, default=""
    )

    transaction: Mapped["Transaction"] = relationship("Transaction", back_populates="splits")
    category: Mapped["Category | None"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Category"
    )
