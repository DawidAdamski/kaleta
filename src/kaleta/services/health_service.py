# SPDX-License-Identifier: AGPL-3.0-or-later
"""Application health checks for local monitors and uptime probes."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta import __version__
from kaleta.config import settings
from kaleta.crypto import key_ring
from kaleta.models.tenant import Tenant, TenantStatus
from kaleta.schemas.health import AuthBackendName
from kaleta.services.setup_service import (
    current_revision,
    head_revision,
    tenants_pending_migration,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class HealthSnapshot:
    """Result of a single health probe."""

    status: str
    version: str
    database_ok: bool
    migrations_pending: bool
    #: ``None`` when the revisions could not be read.
    tenants_pending_migration: int | None = None
    auth_backend: AuthBackendName = "local"
    #: Unlocked sessions in this process's key ring — a count, never a key.
    keyring_sessions: int = 0
    #: ``None`` when the registry could not be read.
    suspended_tenants: list[int] | None = field(default=None)


class HealthService:
    """Probe DB reachability and alembic drift (report-only; does not migrate)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def check(self) -> HealthSnapshot:
        database_ok = await self._database_reachable()
        migrations_pending = False
        tenants_pending: int | None = None
        suspended: list[int] | None = None
        if database_ok:
            migrations_pending, tenants_pending = self._pending()
            suspended = await self._suspended_tenants()
        status = "ok" if database_ok else "error"
        return HealthSnapshot(
            status=status,
            version=__version__,
            database_ok=database_ok,
            migrations_pending=migrations_pending,
            tenants_pending_migration=tenants_pending,
            auth_backend=settings.auth_backend,
            keyring_sessions=key_ring.count(),
            suspended_tenants=suspended,
        )

    async def _suspended_tenants(self) -> list[int] | None:
        """Ids of suspended accounts, read from the registry on this public session."""
        try:
            result = await self.session.execute(
                select(Tenant.id).where(Tenant.status == TenantStatus.SUSPENDED).order_by(Tenant.id)
            )
        except Exception:
            logger.exception("Health check: could not read suspended tenants")
            return None
        return list(result.scalars().all())

    def _pending(self) -> tuple[bool, int | None]:
        """Registry or any family behind head; and how many families are.

        The session here has no tenant schema (``get_public_session``), so the
        revisions are read per schema from the configured URL.
        """
        db_url = settings.db_url
        try:
            registry_behind = current_revision(db_url, public=True) != head_revision(public=True)
            pending = len(tenants_pending_migration(db_url))
        except Exception:
            logger.exception("Health check: could not compare tenant alembic revisions")
            return True, None
        return registry_behind or pending > 0, pending

    async def _database_reachable(self) -> bool:
        try:
            await self.session.execute(text("SELECT 1"))
        except Exception:
            logger.exception("Health check: database unreachable")
            return False
        return True
