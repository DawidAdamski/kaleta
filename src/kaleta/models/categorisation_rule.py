# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import enum

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kaleta.db.base import Base
from kaleta.models.mixins import TimestampMixin, UserOwnedMixin


class RuleMatchMode(str, enum.Enum):  # noqa: UP042
    CONTAINS = "contains"


class CategorisationRule(TimestampMixin, UserOwnedMixin, Base):
    __tablename__ = "categorisation_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    pattern: Mapped[str] = mapped_column(String(200), nullable=False)
    match_mode: Mapped[RuleMatchMode] = mapped_column(
        SAEnum(RuleMatchMode, native_enum=False),
        nullable=False,
        default=RuleMatchMode.CONTAINS,
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    category: Mapped[Category] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Category"
    )

    def __repr__(self) -> str:
        return (
            f"<CategorisationRule id={self.id} pattern={self.pattern!r} "
            f"category_id={self.category_id}>"
        )
