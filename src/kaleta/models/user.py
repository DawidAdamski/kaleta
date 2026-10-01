# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import UTC, datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from kaleta.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    #: ``NULL`` for a member of a hosted account: Supabase Auth holds the
    #: credential, and ``LocalAuthProvider`` refuses to sign such a row in.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: The member's e-mail on a hosted account (also their ``username`` there).
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    #: What the household sees this member as; theirs to edit.
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )
    #: Sessions signed in before this moment are no longer honoured. Bumped by
    #: every credential change; ``NULL`` means no session was ever revoked.
    sessions_valid_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r}>"
