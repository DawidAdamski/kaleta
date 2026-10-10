# SPDX-License-Identifier: AGPL-3.0-or-later
"""Background retention cleanup for anonymous app error events and bug reports.

Both tables live with the household's data — in every tenant schema on the
registry layout — so on that layout one sweep visits each active family in
turn (``postgres-only``, decisions for B2).
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from kaleta.db import AsyncSessionFactory
from kaleta.db.tenant_context import TenantContext, use_tenant
from kaleta.models.tenant import TenantStatus
from kaleta.services.bug_report_service import (
    BugReportService,
    bug_report_retention_days,
    bug_reports_enabled,
)
from kaleta.services.event_service import EventService, instance_events_enabled, retention_days
from kaleta.services.tenant_service import TenantService

logger = logging.getLogger(__name__)

_RETENTION_INTERVAL_SECONDS = 24 * 3600


class EventRetentionScheduler:
    """Run retention purge on startup and once per day."""

    _task: asyncio.Task[None] | None = None

    @classmethod
    def start(cls) -> None:
        if not instance_events_enabled() and not bug_reports_enabled():
            logger.debug("Retention scheduler not started (events and bug reports both off)")
            return
        if cls._task is not None and not cls._task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("Event retention scheduler start skipped: no running event loop")
            return
        cls._task = loop.create_task(cls._loop(), name="kaleta-event-retention")
        logger.info(
            "Event retention scheduler started (retention=%s days)",
            retention_days(),
        )

    @classmethod
    async def stop(cls) -> None:
        task = cls._task
        cls._task = None
        if task is None:
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    @classmethod
    async def _loop(cls) -> None:
        await cls._purge_once()
        while True:
            await asyncio.sleep(_RETENTION_INTERVAL_SECONDS)
            await cls._purge_once()

    @classmethod
    async def _purge_once(cls) -> None:
        """Expire anonymous events and bug reports — each on its own window.

        In every active family; one family failing does not stop the others.
        Suspended families (a schema that did not migrate) are skipped until
        they are resumed.
        """
        try:
            async with AsyncSessionFactory.public() as registry:
                tenants = await TenantService(registry).list_tenants()
        except Exception:
            logger.exception("Retention purge failed: could not list families")
            return
        for tenant in tenants:
            if tenant.status is not TenantStatus.ACTIVE:
                continue
            with use_tenant(TenantContext(tenant_id=tenant.id, schema=tenant.schema_name)):
                await cls._purge_current(where=f" in family {tenant.id}")

    @classmethod
    async def _purge_current(cls, *, where: str = "") -> None:
        days = retention_days()
        report_days = bug_report_retention_days()
        try:
            async with AsyncSessionFactory() as session:
                deleted = (
                    await EventService(session).purge_older_than(days)
                    if instance_events_enabled()
                    else 0
                )
                reports = (
                    await BugReportService(session).purge_older_than(report_days)
                    if bug_reports_enabled()
                    else 0
                )
            if deleted:
                logger.info("Purged %s app event(s) older than %s days%s", deleted, days, where)
            if reports:
                logger.info(
                    "Purged %s bug report(s) older than %s days%s", reports, report_days, where
                )
        except Exception:
            logger.exception("Retention purge failed%s", where)
