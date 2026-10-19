# SPDX-License-Identifier: AGPL-3.0-or-later
"""Application health checks for local monitors and uptime probes."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace

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
    """Result of a single health probe.

    Only ``status`` and ``database_ok`` are always filled; the rest are tier-gated
    (see :meth:`HealthService.check`) and left ``None`` when the caller is not
    entitled to them, so the HTTP layer can omit them.
    """

    status: str
    database_ok: bool
    #: Family tier and up.
    version: str | None = None
    #: Family tier and up; ``None`` when the revisions could not be read.
    migrations_pending: bool | None = None
    #: Admin tier only; ``None`` when the revisions could not be read.
    tenants_pending_migration: int | None = None
    #: Family tier and up.
    auth_backend: AuthBackendName | None = None
    #: Admin tier only — unlocked sessions in this process's key ring, a count, never a key.
    keyring_sessions: int | None = None
    #: Admin tier only; ``None`` when the registry could not be read.
    suspended_tenants: list[int] | None = field(default=None)


class HealthService:
    """Probe DB reachability and alembic drift (report-only; does not migrate)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def check(self, *, include_family: bool, include_admin: bool) -> HealthSnapshot:
        """A health snapshot, filled to the caller's disclosure tier (KAL-SEC-001).

        Both flags are required (no fail-open default): every caller states the
        tier it is entitled to. The public tier (both flags ``False``) does no
        registry reads at all —
        only the liveness ``SELECT 1``. ``include_family`` adds the version, the
        sign-in backend and the ``migrations_pending`` boolean. ``include_admin``
        adds the cross-family operational state: the pending-migration count, the
        keyring-session count and the suspended-family ids.
        """
        database_ok = await self._database_reachable()
        status = "ok" if database_ok else "error"
        snapshot = HealthSnapshot(status=status, database_ok=database_ok)
        if not include_family and not include_admin:
            return snapshot

        migrations_pending: bool | None = None
        tenants_pending: int | None = None
        if database_ok:
            migrations_pending, tenants_pending = self._pending()
        snapshot = replace(
            snapshot,
            version=__version__,
            auth_backend=settings.auth_backend,
            migrations_pending=migrations_pending,
        )
        if not include_admin:
            return snapshot

        suspended = await self._suspended_tenants() if database_ok else None
        return replace(
            snapshot,
            tenants_pending_migration=tenants_pending,
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
