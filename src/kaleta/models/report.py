# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from sqlalchemy.orm import Mapped, mapped_column

from kaleta.db.base import Base
from kaleta.db.types import EncryptedText
from kaleta.models.mixins import TimestampMixin, UserOwnedMixin


class SavedReport(TimestampMixin, UserOwnedMixin, Base):
    __tablename__ = "saved_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(EncryptedText("saved_reports.name"), nullable=False)
    # JSON-serialised ReportConfig dict
    config: Mapped[str] = mapped_column(EncryptedText("saved_reports.config"), nullable=False)

    def __repr__(self) -> str:
        return f"<SavedReport id={self.id} name={self.name!r}>"
