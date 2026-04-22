from __future__ import annotations

import datetime

from sqlalchemy import Boolean, DateTime, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from kaleta.db.base import Base
from kaleta.models.mixins import TimestampMixin


class MonthlyReadiness(TimestampMixin, Base):
    """Progress state for the Monthly Readiness wizard section, one row per month.

    Each of the four stages has an independent completion flag so the user can
    work the checklist in any order. ``ready_at`` stamps the moment all four
    stages were marked done; ``seen_planned_ids`` persists stage 4's per-row
    acknowledgement state (a JSON list of PlannedTransaction ids).
    """

    __tablename__ = "monthly_readiness"
    __table_args__ = (
        UniqueConstraint("year", "month", name="uq_monthly_readiness_year_month"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    stage_1_done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    stage_2_done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    stage_3_done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    stage_4_done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    seen_planned_ids: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    ready_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<MonthlyReadiness year={self.year} month={self.month}>"
