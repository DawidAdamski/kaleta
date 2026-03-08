from __future__ import annotations

import enum

from sqlalchemy import Enum as SAEnum
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kaleta.db.base import Base
from kaleta.models.mixins import TimestampMixin


class InstitutionType(str, enum.Enum):
    BANK = "bank"
    FINTECH = "fintech"
    CREDIT_UNION = "credit_union"
    BROKER = "broker"
    INSURANCE = "insurance"
    OTHER = "other"


class Institution(TimestampMixin, Base):
    __tablename__ = "institutions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    type: Mapped[InstitutionType] = mapped_column(
        SAEnum(InstitutionType, native_enum=False), nullable=False, default=InstitutionType.BANK
    )
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)   # hex e.g. #1976d2
    website: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    accounts: Mapped[list[Account]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Account", back_populates="institution"
    )

    def __repr__(self) -> str:
        return f"<Institution id={self.id} name={self.name!r} type={self.type}>"
