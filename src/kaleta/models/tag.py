# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from typing import ClassVar

from sqlalchemy import Column, ForeignKey, Integer, String, Table, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kaleta.db.base import Base
from kaleta.db.blind_index import BlindIndexSpec
from kaleta.db.types import EncryptedText, exact_index
from kaleta.models.mixins import TimestampMixin, UserOwnedMixin

# Association table — no ORM class, just a plain Table
transaction_tags = Table(
    "transaction_tags",
    Base.metadata,
    Column(
        "transaction_id",
        Integer,
        ForeignKey("transactions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "tag_id",
        Integer,
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Tag(TimestampMixin, UserOwnedMixin, Base):
    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("name_bidx", name="uq_tags_name_bidx"),)
    __blind_indexes__: ClassVar[BlindIndexSpec] = {"name_bidx": ("name", exact_index)}

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(EncryptedText("tags.name"), nullable=False)
    name_bidx: Mapped[str | None] = mapped_column(String(64), nullable=True)
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    icon: Mapped[str | None] = mapped_column(String(50), nullable=True)
    description: Mapped[str | None] = mapped_column(
        EncryptedText("tags.description"), nullable=True
    )

    transactions: Mapped[list[Transaction]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Transaction", secondary=transaction_tags, back_populates="tags"
    )

    def __repr__(self) -> str:
        return f"<Tag id={self.id} name={self.name!r}>"
