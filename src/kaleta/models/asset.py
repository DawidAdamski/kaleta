from __future__ import annotations

import datetime
import enum
from decimal import Decimal

from sqlalchemy import Date, Numeric, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from kaleta.db.base import Base
from kaleta.models.mixins import TimestampMixin


class AssetType(str, enum.Enum):  # noqa: UP042
    REAL_ESTATE = "real_estate"
    VEHICLE = "vehicle"
    VALUABLES = "valuables"
    OTHER = "other"


class Asset(TimestampMixin, Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[AssetType] = mapped_column(
        SAEnum(AssetType, native_enum=False), nullable=False, default=AssetType.OTHER
    )
    value: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2), nullable=False, default=Decimal("0.00")
    )
    description: Mapped[str] = mapped_column(String(500), nullable=False, server_default="")
    purchase_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    purchase_price: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=15, scale=2), nullable=True
    )

    def __repr__(self) -> str:
        return f"<Asset id={self.id} name={self.name!r} type={self.type} value={self.value}>"
