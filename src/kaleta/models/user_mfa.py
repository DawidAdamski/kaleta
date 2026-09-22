# SPDX-License-Identifier: AGPL-3.0-or-later
"""The second factor bound to a user account."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from kaleta.db.base import Base
from kaleta.db.types import EncryptedString

#: The only factor kind this release enrols. The column exists so that
#: WebAuthn can be added as a second row rather than a second table.
MFA_KIND_TOTP = "totp"


class UserMfa(Base):
    __tablename__ = "user_mfa"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    kind: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=MFA_KIND_TOTP,
        server_default=MFA_KIND_TOTP,
    )
    totp_secret: Mapped[str] = mapped_column(
        EncryptedString(aad="user_mfa.totp_secret"),
        nullable=False,
    )
    #: ``None`` until the first correct code proves the authenticator app
    #: really holds the secret. An unconfirmed row never guards a login.
    enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: The TOTP step number last accepted. A code is single-use: replaying it
    #: inside its own 30-second window is rejected.
    last_used_counter: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    #: JSON list of argon2 hashes, one per unused recovery code.
    recovery_codes_hash: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
        server_default="[]",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        # Never the secret, never the hashes: this ends up in logs.
        return f"<UserMfa user_id={self.user_id} kind={self.kind!r} enabled={self.is_enabled}>"

    @property
    def is_enabled(self) -> bool:
        return self.enabled_at is not None
