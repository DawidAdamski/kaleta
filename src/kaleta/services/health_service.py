# SPDX-License-Identifier: AGPL-3.0-or-later
"""Application health checks for local monitors and uptime probes."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from kaleta import __version__
from kaleta.config import settings
from kaleta.config.setup_config import get_db_url
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
    #: ``None`` on a single-tenant install.
    tenants_pending_migration: int | None = None


class HealthService:
    """Probe DB reachability and alembic drift (report-only; does not migrate)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def check(self) -> HealthSnapshot:
        database_ok = await self._database_reachable()
        migrations_pending = False
        tenants_pending: int | None = None
        if database_ok:
            if settings.tenancy == "multi":
                migrations_pending, tenants_pending = self._multi_tenant_pending()
            else:
                migrations_pending = self._migrations_pending()
        status = "ok" if database_ok else "error"
        return HealthSnapshot(
            status=status,
            version=__version__,
            database_ok=database_ok,
            migrations_pending=migrations_pending,
            tenants_pending_migration=tenants_pending,
        )

    def _multi_tenant_pending(self) -> tuple[bool, int | None]:
        """Registry or any tenant behind head; and how many tenants are.

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

    def _migrations_pending(self) -> bool:
        db_url = self._resolved_db_url()
        try:
            head = head_revision()
            current = current_revision(db_url)
        except Exception:
            logger.exception("Health check: could not compare alembic revisions")
            # Treat revision readout failure as pending so monitors notice drift.
            return True
        return current != head

    def _resolved_db_url(self) -> str:
        """Prefer the live session bind URL so probes match the engine in use."""
        bind = self.session.bind
        if isinstance(bind, AsyncEngine):
            return bind.url.render_as_string(hide_password=False)
        if isinstance(bind, AsyncConnection):
            return bind.engine.url.render_as_string(hide_password=False)
        return get_db_url() or settings.db_url
