import enum
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Index, Numeric, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kaleta.db.base import Base
from kaleta.models.mixins import TimestampMixin
from kaleta.models.tag import transaction_tags


class TransactionType(str, enum.Enum):  # noqa: UP042
    INCOME = "income"
    EXPENSE = "expense"
    TRANSFER = "transfer"


class Transaction(TimestampMixin, Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    # Self-referential FK for linking paired internal transfer legs
    linked_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id"), nullable=True
    )

    amount: Mapped[Decimal] = mapped_column(Numeric(precision=15, scale=2), nullable=False)
    # For cross-currency transfers: how many dest-currency units per 1 src-currency unit
    exchange_rate: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=15, scale=6), nullable=True
    )
    type: Mapped[TransactionType] = mapped_column(SAEnum(TransactionType, native_enum=False), nullable=False)  # noqa: E501
    date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    is_internal_transfer: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_split: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    account: Mapped["Account"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Account", back_populates="transactions"
    )
    category: Mapped["Category | None"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Category", back_populates="transactions"
    )
    linked_transaction: Mapped["Transaction | None"] = relationship(
        "Transaction", remote_side="Transaction.id", foreign_keys=[linked_transaction_id]
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
    __table_args__ = (
        Index("ix_transaction_splits_transaction_id", "transaction_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False
    )
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(precision=15, scale=2), nullable=False)
    note: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    transaction: Mapped["Transaction"] = relationship("Transaction", back_populates="splits")
    category: Mapped["Category | None"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Category"
    )
