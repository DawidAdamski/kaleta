# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import enum
from typing import ClassVar

from sqlalchemy import Enum as SAEnum
from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kaleta.db.base import Base
from kaleta.db.blind_index import BlindIndexSpec
from kaleta.db.types import EncryptedText, blind_index
from kaleta.models.mixins import TimestampMixin


class InstitutionType(enum.StrEnum):
    BANK = "bank"
    FINTECH = "fintech"
    CREDIT_UNION = "credit_union"
    BROKER = "broker"
    INSURANCE = "insurance"
    OTHER = "other"


class Institution(TimestampMixin, Base):
    __tablename__ = "institutions"
    __table_args__ = (UniqueConstraint("name_bidx", name="uq_institutions_name_bidx"),)
    __blind_indexes__: ClassVar[BlindIndexSpec] = {"name_bidx": ("name", blind_index)}

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(EncryptedText("institutions.name"), nullable=False)
    name_bidx: Mapped[str | None] = mapped_column(String(64), nullable=True)
    type: Mapped[InstitutionType] = mapped_column(
        SAEnum(InstitutionType, native_enum=False), nullable=False, default=InstitutionType.BANK
    )
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)  # hex e.g. #1976d2
    website: Mapped[str | None] = mapped_column(
        EncryptedText("institutions.website"), nullable=True
    )
    description: Mapped[str | None] = mapped_column(
        EncryptedText("institutions.description"), nullable=True
    )
    logo_path: Mapped[str | None] = mapped_column(String(255), nullable=True)

    accounts: Mapped[list[Account]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Account", back_populates="institution"
    )

    def __repr__(self) -> str:
        return f"<Institution id={self.id} name={self.name!r} type={self.type}>"
