from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kaleta.db.base import Base
from kaleta.models.mixins import TimestampMixin


class Payee(TimestampMixin, Base):
    __tablename__ = "payees"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    transactions: Mapped[list[Transaction]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Transaction", back_populates="payee"
    )

    def __repr__(self) -> str:
        return f"<Payee id={self.id} name={self.name!r}>"
