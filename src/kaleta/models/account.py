# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import enum
from decimal import Decimal
from typing import ClassVar

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kaleta.db.base import Base
from kaleta.db.blind_index import BlindIndexSpec
from kaleta.db.types import EncryptedText, account_suffix_index, blind_index_digits
from kaleta.models.mixins import TimestampMixin, UserOwnedMixin


class AccountType(enum.StrEnum):
    CHECKING = "checking"
    SAVINGS = "savings"
    CASH = "cash"
    CREDIT = "credit"


class Account(TimestampMixin, UserOwnedMixin, Base):
    """A place money sits.

    There is no stored balance. ``opening_balance`` is what the account held
    before its first transaction; the current balance is that plus the
    signed sum of the ledger, computed by ``AccountService.balances``.
    """

    __tablename__ = "accounts"
    __blind_indexes__: ClassVar[BlindIndexSpec] = {
        "external_account_number_bidx": ("external_account_number", blind_index_digits),
        "external_account_number_sfx_bidx": ("external_account_number", account_suffix_index),
    }

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(EncryptedText("accounts.name"), nullable=False)
    type: Mapped[AccountType] = mapped_column(
        SAEnum(AccountType, native_enum=False), nullable=False, default=AccountType.CHECKING
    )
    opening_balance: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2), nullable=False, default=Decimal("0.00")
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="PLN")
    institution_id: Mapped[int | None] = mapped_column(
        ForeignKey("institutions.id", ondelete="SET NULL"), nullable=True
    )
    external_account_number: Mapped[str | None] = mapped_column(
        EncryptedText("accounts.external_account_number"), nullable=True
    )
    #: Blind index of the number's digits, and of its last eight (ADR-20
    #: suffix matching) — equality without the number.
    external_account_number_bidx: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    external_account_number_sfx_bidx: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )

    institution: Mapped[Institution | None] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Institution", back_populates="accounts"
    )
    transactions: Mapped[list[Transaction]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Transaction", back_populates="account", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Account id={self.id} name={self.name!r} type={self.type}>"
