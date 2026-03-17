from __future__ import annotations

import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from kaleta.db.base import Base

MAX_AUDIT_ENTRIES: int = 100


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime.datetime] = mapped_column(
        DateTime(), nullable=False, default=func.now()
    )
    operation: Mapped[str] = mapped_column(String(10), nullable=False)  # INSERT UPDATE DELETE
    table_name: Mapped[str] = mapped_column(String(100), nullable=False)
    record_id: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    old_data: Mapped[str | None] = mapped_column(Text(), nullable=True)  # JSON
    new_data: Mapped[str | None] = mapped_column(Text(), nullable=True)  # JSON
    reverted: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
