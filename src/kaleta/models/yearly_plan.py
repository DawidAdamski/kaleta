from __future__ import annotations

from sqlalchemy import Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from kaleta.db.base import Base
from kaleta.models.mixins import TimestampMixin


class YearlyPlan(TimestampMixin, Base):
    """A yearly budget intent — decomposes into 12 monthly Budget rows.

    Plan lines are stored as JSON strings for v1. Each *_lines column
    holds a JSON array of objects (see kaleta.schemas.yearly_plan for
    shape). Versioning revisits are cheap because there is at most one
    row per year (unique constraint).
    """

    __tablename__ = "yearly_plans"
    __table_args__ = (UniqueConstraint("year", name="uq_yearly_plans_year"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    income_lines: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    fixed_lines: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    variable_lines: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    reserves_lines: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    def __repr__(self) -> str:
        return f"<YearlyPlan id={self.id} year={self.year}>"
