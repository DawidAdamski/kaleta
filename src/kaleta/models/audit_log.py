# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from kaleta.db.base import Base
from kaleta.db.types import EncryptedText

MAX_AUDIT_ENTRIES: int = 100


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime.datetime] = mapped_column(
        DateTime(), nullable=False, default=func.now(), index=True
    )
    operation: Mapped[str] = mapped_column(String(10), nullable=False)  # INSERT UPDATE DELETE
    table_name: Mapped[str] = mapped_column(String(100), nullable=False)
    record_id: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    # JSON snapshots of mapped attributes — plaintext, so the whole blob is
    # encrypted. Auth events written before an unlock are the one exception
    # (see ``EncryptedText.plaintext_while_locked``).
    old_data: Mapped[str | None] = mapped_column(
        EncryptedText("audit_log.old_data", plaintext_while_locked=True), nullable=True
    )
    new_data: Mapped[str | None] = mapped_column(
        EncryptedText("audit_log.new_data", plaintext_while_locked=True), nullable=True
    )
    reverted: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
