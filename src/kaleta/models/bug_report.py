# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import enum
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from kaleta.db.base import Base


class BugReportStatus(enum.StrEnum):
    NEW = "new"
    SEEN = "seen"
    CLOSED = "closed"


class BugReport(Base):
    """A problem report a user chose to send, with the diagnostics they agreed to.

    Everything here is operator data: the user typed the summary and the
    description themselves, and nothing is copied out of the ledger.
    """

    __tablename__ = "bug_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[str] = mapped_column(String(16), nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        default=lambda: datetime.now(UTC),
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    contact_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    summary: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text(), nullable=False)
    event_ids: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    route: Mapped[str | None] = mapped_column(String(260), nullable=True)
    app_version: Mapped[str] = mapped_column(String(40), nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    viewport: Mapped[str | None] = mapped_column(String(40), nullable=True)
    locale: Mapped[str | None] = mapped_column(String(20), nullable=True)
    #: The session ring buffer as JSON text — only when the user ticked the box.
    log_excerpt: Mapped[str | None] = mapped_column(Text(), nullable=True)
    status: Mapped[BugReportStatus] = mapped_column(
        SAEnum(BugReportStatus, native_enum=False),
        nullable=False,
        default=BugReportStatus.NEW,
    )
    external_ref: Mapped[str | None] = mapped_column(String(300), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<BugReport id={self.id} report_id={self.report_id!r} "
            f"status={self.status!r} created_at={self.created_at}>"
        )
