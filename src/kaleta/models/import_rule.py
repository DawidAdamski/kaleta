# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kaleta.db.base import Base
from kaleta.models.mixins import TimestampMixin, UserOwnedMixin


class ImportRule(TimestampMixin, UserOwnedMixin, Base):
    """Filename-pattern memory for CSV import account + column mapping."""

    __tablename__ = "import_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename_pattern: Mapped[str] = mapped_column(String(200), nullable=False)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Keyed dict: {"date": 0, "amount": 2, ...} — see ColumnMapping.to_dict()
    column_mapping: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    encoding: Mapped[str | None] = mapped_column(String(40), nullable=True)
    delimiter: Mapped[str | None] = mapped_column(String(8), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    account: Mapped[Account] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Account"
    )

    def __repr__(self) -> str:
        return (
            f"<ImportRule id={self.id} pattern={self.filename_pattern!r} "
            f"account_id={self.account_id}>"
        )
