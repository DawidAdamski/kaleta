# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kaleta.db.base import Base
from kaleta.db.blind_index import BlindIndexSpec
from kaleta.db.types import EncryptedText, blind_index
from kaleta.models.mixins import TimestampMixin, UserOwnedMixin

if TYPE_CHECKING:
    from kaleta.models.payee_identity import PayeeIdentity


class Payee(TimestampMixin, UserOwnedMixin, Base):
    __tablename__ = "payees"
    __table_args__ = (UniqueConstraint("name_bidx", name="uq_payees_name_bidx"),)
    __blind_indexes__: ClassVar[BlindIndexSpec] = {"name_bidx": ("name", blind_index)}

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(EncryptedText("payees.name"), nullable=False)
    name_bidx: Mapped[str | None] = mapped_column(String(64), nullable=True)
    website: Mapped[str | None] = mapped_column(EncryptedText("payees.website"), nullable=True)
    address: Mapped[str | None] = mapped_column(EncryptedText("payees.address"), nullable=True)
    city: Mapped[str | None] = mapped_column(EncryptedText("payees.city"), nullable=True)
    country: Mapped[str | None] = mapped_column(EncryptedText("payees.country"), nullable=True)
    email: Mapped[str | None] = mapped_column(EncryptedText("payees.email"), nullable=True)
    phone: Mapped[str | None] = mapped_column(EncryptedText("payees.phone"), nullable=True)
    notes: Mapped[str | None] = mapped_column(EncryptedText("payees.notes"), nullable=True)

    transactions: Mapped[list[Transaction]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Transaction", back_populates="payee"
    )
    identities: Mapped[list[PayeeIdentity]] = relationship(
        "PayeeIdentity",
        back_populates="payee",
        cascade="all, delete-orphan",
        order_by="PayeeIdentity.id",
    )

    def __repr__(self) -> str:
        return f"<Payee id={self.id} name={self.name!r}>"
