# SPDX-License-Identifier: AGPL-3.0-or-later
"""Gift planning as a yearly grid: people down the side, occasions across.

A cell is one person's gift for one occasion in one year. An empty cell is a
missing row, not a zero, so "nothing planned" and "planned at 0.00" differ.
Names and notes are user text, so they are encrypted — ordering and duplicate
checks therefore happen in Python, not SQL.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from kaleta.db.base import Base
from kaleta.db.types import EncryptedText
from kaleta.models.mixins import TimestampMixin, UserOwnedMixin


class GiftPerson(TimestampMixin, UserOwnedMixin, Base):
    """A row of the grid. Archived people keep their past years' cells."""

    __tablename__ = "gift_people"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(EncryptedText("gift_people.name"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    def __repr__(self) -> str:
        return f"<GiftPerson id={self.id}>"


class GiftOccasion(TimestampMixin, UserOwnedMixin, Base):
    """A column of the grid, shared by every person and every year."""

    __tablename__ = "gift_occasions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(EncryptedText("gift_occasions.name"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    def __repr__(self) -> str:
        return f"<GiftOccasion id={self.id}>"


class GiftCell(TimestampMixin, UserOwnedMixin, Base):
    """How much to set aside for one person's gift on one occasion in one year.

    A ledger expense marks it bought by pointing ``Transaction.gift_id`` at it
    (``KAL-GFT-003``).
    """

    __tablename__ = "gift_cells"
    __table_args__ = (
        UniqueConstraint("year", "person_id", "occasion_id", name="uq_gift_cells_slot"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    person_id: Mapped[int] = mapped_column(
        ForeignKey("gift_people.id", ondelete="CASCADE"), nullable=False, index=True
    )
    occasion_id: Mapped[int] = mapped_column(
        ForeignKey("gift_occasions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(precision=15, scale=2), nullable=False)
    note: Mapped[str | None] = mapped_column(EncryptedText("gift_cells.note"), nullable=True)

    def __repr__(self) -> str:
        return f"<GiftCell id={self.id} year={self.year}>"
