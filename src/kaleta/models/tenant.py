# SPDX-License-Identifier: AGPL-3.0-or-later
"""The cross-tenant registry of the hosted layout (ADR-35).

Lives in ``public`` on ``PublicBase`` — never in ``Base.metadata``, so no tenant
schema ever contains it — and exists only in ``KALETA_TENANCY=multi``. It holds
no financial data: which schema an account lives in, and per member the auth
subject, e-mail, role and (filled by ``hosted-field-encryption``) key material.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kaleta.db.base import PublicBase
from kaleta.db.tenant_schemas import PUBLIC_SCHEMA

_PUBLIC = {"schema": PUBLIC_SCHEMA}


class TenantStatus(enum.StrEnum):
    PROVISIONING = "provisioning"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REKEYING = "rekeying"
    DELETING = "deleting"


class TenantRole(enum.StrEnum):
    OWNER = "owner"
    MEMBER = "member"


class TenantMemberStatus(enum.StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    REMOVED = "removed"


def _now() -> datetime:
    return datetime.now(UTC)


def _enum(cls: type[enum.StrEnum], name: str) -> Enum:
    # Stored as plain strings (no Postgres ENUM type): the registry migrates in
    # its own environment and a new status must not need an ALTER TYPE.
    return Enum(
        cls,
        name=name,
        native_enum=False,
        length=20,
        values_callable=lambda members: [m.value for m in members],
    )


class Tenant(PublicBase):
    __tablename__ = "tenants"
    __table_args__ = _PUBLIC

    id: Mapped[int] = mapped_column(primary_key=True)
    schema_name: Mapped[str] = mapped_column(String(63), nullable=False, unique=True)
    #: The household's name. Encrypted by ``hosted-field-encryption``.
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[TenantStatus] = mapped_column(
        _enum(TenantStatus, "tenant_status"), nullable=False, default=TenantStatus.PROVISIONING
    )
    key_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, server_default=func.now()
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    members: Mapped[list[TenantMember]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan", passive_deletes=True
    )

    def __repr__(self) -> str:
        return f"<Tenant id={self.id} schema={self.schema_name!r} status={self.status.value}>"


class TenantMember(PublicBase):
    __tablename__ = "tenant_members"
    __table_args__ = _PUBLIC

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey(f"{PUBLIC_SCHEMA}.tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: The identity provider's opaque id. One identity belongs to one tenant.
    auth_subject: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    #: Lower-cased.
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    role: Mapped[TenantRole] = mapped_column(_enum(TenantRole, "tenant_role"), nullable=False)
    status: Mapped[TenantMemberStatus] = mapped_column(
        _enum(TenantMemberStatus, "tenant_member_status"),
        nullable=False,
        default=TenantMemberStatus.PENDING,
    )
    #: The member's row in the tenant schema's own ``users`` table.
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Key material, filled by `hosted-field-encryption`; created now so the
    # registry needs one migration, not two.
    public_key: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    private_key_wrapped: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    private_key_salt: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    kdf_params: Mapped[str | None] = mapped_column(Text, nullable=True)
    recovery_wrapped: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    recovery_salt: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    dek_sealed: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    tenant: Mapped[Tenant] = relationship(back_populates="members")

    def __repr__(self) -> str:
        return (
            f"<TenantMember id={self.id} tenant_id={self.tenant_id} role={self.role.value} "
            f"status={self.status.value}>"
        )


class TenantInvite(PublicBase):
    """An invitation to join a household — used by ``hosted-household-sharing``."""

    __tablename__ = "tenant_invites"
    __table_args__ = (UniqueConstraint("token_hash"), _PUBLIC)

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey(f"{PUBLIC_SCHEMA}.tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[TenantRole] = mapped_column(_enum(TenantRole, "tenant_role"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LocalIdentity(PublicBase):
    """A login of ``KALETA_AUTH_BACKEND=local`` on the registry layout (ADR-38).

    The password lives here, not in a tenant's ``users`` table: one login maps
    to one family through ``tenant_members.auth_subject`` (``local:<id>``), and
    the instance administrator is a login that may belong to no family at all.
    """

    __tablename__ = "local_identities"
    __table_args__ = _PUBLIC

    id: Mapped[int] = mapped_column(primary_key=True)
    #: Lower-cased.
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_instance_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    disabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: Reserved for ``instance-admin-panel`` (a reset the user must change at
    #: the next sign-in); nothing sets or reads it yet.
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, server_default=func.now()
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def subject(self) -> str:
        return f"local:{self.id}"

    def __repr__(self) -> str:
        return f"<LocalIdentity id={self.id} admin={self.is_instance_admin}>"


class InstanceSetting(PublicBase):
    """One instance-wide setting, e.g. ``registration_mode`` (ADR-38)."""

    __tablename__ = "instance_settings"
    __table_args__ = _PUBLIC

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
