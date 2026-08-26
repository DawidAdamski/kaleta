# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kaleta.db.base import Base


class AppEvent(Base):
    """Anonymous application error event for maintainer diagnostics."""

    __tablename__ = "app_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[str] = mapped_column(String(16), nullable=False, unique=True, index=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        default=lambda: datetime.now(UTC),
    )
    level: Mapped[str] = mapped_column(String(10), nullable=False)
    route: Mapped[str | None] = mapped_column(String(260), nullable=True)
    exception_class: Mapped[str] = mapped_column(String(200), nullable=False)
    stack_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    stack_trace: Mapped[str] = mapped_column(Text(), nullable=False)
    app_version: Mapped[str] = mapped_column(String(40), nullable=False)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    user: Mapped[User | None] = relationship("User")  # type: ignore[name-defined]  # noqa: F821

    def __repr__(self) -> str:
        return (
            f"<AppEvent id={self.id} event_id={self.event_id!r} "
            f"level={self.level!r} occurred_at={self.occurred_at}>"
        )
