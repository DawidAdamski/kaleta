from __future__ import annotations

import datetime
import enum
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from kaleta.db.base import Base
from kaleta.models.mixins import TimestampMixin


class ReserveFundKind(enum.StrEnum):
    EMERGENCY = "emergency"
    IRREGULAR = "irregular"
    VACATION = "vacation"


class ReserveFundBackingMode(enum.StrEnum):
    ACCOUNT = "account"
    ENVELOPE = "envelope"


class ReserveFund(TimestampMixin, Base):
    """A dedicated reserve fund the user tracks progress against.

    Backing mode declares where the current balance comes from:
    - ``account`` → sum of `backing_account_id`'s balance.
    - ``envelope`` → reserved for future category-tagged envelopes;
      not offered in the v1 UI.
    """

    __tablename__ = "reserve_funds"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    kind: Mapped[ReserveFundKind] = mapped_column(
        SAEnum(ReserveFundKind, native_enum=False), nullable=False
    )
    target_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2), nullable=False, default=Decimal("0.00")
    )
    backing_mode: Mapped[ReserveFundBackingMode] = mapped_column(
        SAEnum(ReserveFundBackingMode, native_enum=False),
        nullable=False,
        default=ReserveFundBackingMode.ACCOUNT,
    )
    backing_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    backing_category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    emergency_multiplier: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    archived_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<ReserveFund id={self.id} kind={self.kind} name={self.name!r}>"
