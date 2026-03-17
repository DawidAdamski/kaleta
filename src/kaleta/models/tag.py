from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kaleta.db.base import Base
from kaleta.models.mixins import TimestampMixin

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


class Tag(TimestampMixin, Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    icon: Mapped[str | None] = mapped_column(String(50), nullable=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    transactions: Mapped[list[Transaction]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Transaction", secondary=transaction_tags, back_populates="tags"
    )

    def __repr__(self) -> str:
        return f"<Tag id={self.id} name={self.name!r}>"
