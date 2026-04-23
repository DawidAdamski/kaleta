from __future__ import annotations

import datetime
import enum
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from kaleta.db.base import Base
from kaleta.models.mixins import TimestampMixin


class SubscriptionStatus(enum.StrEnum):
    ACTIVE = "active"
    MUTED = "muted"
    CANCELLED = "cancelled"


class Subscription(TimestampMixin, Base):
    """A recurring paid service the user wants to track.

    Links to a payee when one exists; otherwise ``name`` is the
    free-text label. ``cadence_days`` is the expected period between
    charges — commonly ~30 (monthly) or ~365 (yearly).
    """

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    payee_id: Mapped[int | None] = mapped_column(
        ForeignKey("payees.id", ondelete="SET NULL"), nullable=True
    )
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2), nullable=False
    )
    cadence_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    first_seen_at: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    next_expected_at: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    status: Mapped[SubscriptionStatus] = mapped_column(
        SAEnum(SubscriptionStatus, native_enum=False),
        nullable=False,
        default=SubscriptionStatus.ACTIVE,
    )
    muted_until: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    cancelled_at: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    auto_renew: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<Subscription id={self.id} name={self.name!r} "
            f"amount={self.amount} cadence={self.cadence_days}d "
            f"status={self.status}>"
        )
