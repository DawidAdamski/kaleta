# SPDX-License-Identifier: AGPL-3.0-or-later
"""The self-hosted copy of ``tenant_members``' key block (``KALETA_ENCRYPTION=passphrase``).

One row per local user: the same public key, wrapped private key, salts, KDF
parameters, recovery wrap and sealed data key a hosted member carries in
``public.tenant_members`` — nothing here opens anything without the passphrase
or the recovery code.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, LargeBinary, Text
from sqlalchemy.orm import Mapped, mapped_column

from kaleta.db.base import Base


class LocalKeyMaterial(Base):
    __tablename__ = "local_key_material"

    id: Mapped[int] = mapped_column(primary_key=True)
    #: ``users.id`` — deliberately not a foreign key. A backup restore empties
    #: ``users``; an ``ON DELETE CASCADE`` would delete the only copy of the
    #: sealed data key with it, and a restrictive FK would block the restore.
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    #: ``Tenant.key_version``'s counterpart: the header byte of every value
    #: written under this database's data key.
    key_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    public_key: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    private_key_wrapped: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    private_key_salt: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    kdf_params: Mapped[str] = mapped_column(Text, nullable=False)
    recovery_wrapped: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    recovery_salt: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    dek_sealed: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<LocalKeyMaterial user_id={self.user_id} key_version={self.key_version}>"
