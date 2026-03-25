from __future__ import annotations

import enum
from decimal import Decimal

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kaleta.db.base import Base
from kaleta.models.mixins import TimestampMixin


class AccountType(str, enum.Enum):
    CHECKING = "checking"
    SAVINGS = "savings"
    CASH = "cash"
    CREDIT = "credit"


class Account(TimestampMixin, Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[AccountType] = mapped_column(
        SAEnum(AccountType, native_enum=False), nullable=False, default=AccountType.CHECKING
    )
    balance: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2), nullable=False, default=Decimal("0.00")
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="PLN")
    institution_id: Mapped[int | None] = mapped_column(
        ForeignKey("institutions.id", ondelete="SET NULL"), nullable=True
    )
    external_account_number: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )

    institution: Mapped[Institution | None] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Institution", back_populates="accounts"
    )
    transactions: Mapped[list[Transaction]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Transaction", back_populates="account", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Account id={self.id} name={self.name!r} type={self.type}>"
