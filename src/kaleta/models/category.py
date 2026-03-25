from __future__ import annotations

import enum

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kaleta.db.base import Base
from kaleta.models.mixins import TimestampMixin


class CategoryType(str, enum.Enum):  # noqa: UP042
    INCOME = "income"
    EXPENSE = "expense"


class Category(TimestampMixin, Base):
    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("name", "parent_id", name="uq_categories_name_parent"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[CategoryType] = mapped_column(
        SAEnum(CategoryType, native_enum=False), nullable=False
    )
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL", name="fk_categories_parent_id"),
        nullable=True,
    )

    parent: Mapped[Category | None] = relationship(
        "Category", back_populates="children", remote_side="Category.id", foreign_keys=[parent_id]
    )
    children: Mapped[list[Category]] = relationship(
        "Category", back_populates="parent", foreign_keys=[parent_id], cascade="all, delete-orphan"
    )
    transactions: Mapped[list[Transaction]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Transaction", back_populates="category"
    )
    budgets: Mapped[list[Budget]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Budget", back_populates="category", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Category id={self.id} name={self.name!r} type={self.type}>"
