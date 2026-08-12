# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kaleta.db.base import Base
from kaleta.models.mixins import TimestampMixin, UserOwnedMixin


class ImportRun(TimestampMixin, UserOwnedMixin, Base):
    """One completed CSV file import into a single account."""

    __tablename__ = "import_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(String(260), nullable=False)
    profile: Mapped[str] = mapped_column(String(40), nullable=False)
    imported_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    row_date_min: Mapped[date | None] = mapped_column(Date, nullable=True)
    row_date_max: Mapped[date | None] = mapped_column(Date, nullable=True)

    account: Mapped[Account] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Account"
    )

    def __repr__(self) -> str:
        return (
            f"<ImportRun id={self.id} account_id={self.account_id} "
            f"filename={self.filename!r} imported={self.imported_count}>"
        )
