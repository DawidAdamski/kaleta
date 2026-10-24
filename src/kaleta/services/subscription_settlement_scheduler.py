# SPDX-License-Identifier: AGPL-3.0-or-later
"""Background settlement of due subscription cancellations.

A cancellation scheduled for a future date only flips to ``cancelled`` when
``SubscriptionService.settle_due_cancellations`` runs. That used to happen
only on opening ``/wizard/subscriptions``; until then readers that filter on
``status != CANCELLED`` (the unplanned radar, the detector's tracked-payee
set, ``GET /api/v1/subscriptions``) still saw the row as active. Subscriptions
live with the household's data — in every tenant schema on the registry
layout — so one sweep visits each active family in turn (``postgres-only``).
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from kaleta.db import AsyncSessionFactory
from kaleta.db.tenant_context import TenantContext, use_tenant
from kaleta.models.tenant import TenantStatus
from kaleta.services.subscription_service import SubscriptionService
from kaleta.services.tenant_service import TenantService

logger = logging.getLogger(__name__)

_SETTLEMENT_INTERVAL_SECONDS = 24 * 3600


class SubscriptionSettlementScheduler:
    """Settle due subscription cancellations on startup and once per day."""

    _task: asyncio.Task[None] | None = None

    @classmethod
    def start(cls) -> None:
        if cls._task is not None and not cls._task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("Subscription settlement scheduler start skipped: no running event loop")
            return
        cls._task = loop.create_task(cls._loop(), name="kaleta-subscription-settlement")
        logger.info("Subscription settlement scheduler started")

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
        await cls._settle_once()
        while True:
            await asyncio.sleep(_SETTLEMENT_INTERVAL_SECONDS)
            await cls._settle_once()

    @classmethod
    async def _settle_once(cls) -> None:
        """Settle due cancellations in every active family.

        One family failing does not stop the others. Suspended families (a
        schema that did not migrate) are skipped until they are resumed.
        """
        try:
            async with AsyncSessionFactory.public() as registry:
                tenants = await TenantService(registry).list_tenants()
        except Exception:
            logger.exception("Subscription settlement failed: could not list families")
            return
        for tenant in tenants:
            if tenant.status is not TenantStatus.ACTIVE:
                continue
            with use_tenant(TenantContext(tenant_id=tenant.id, schema=tenant.schema_name)):
                await cls._settle_current(where=f" in family {tenant.id}")

    @classmethod
    async def _settle_current(cls, *, where: str = "") -> None:
        try:
            async with AsyncSessionFactory() as session:
                settled = await SubscriptionService(session).settle_due_cancellations()
            if settled:
                logger.info("Settled %s due subscription cancellation(s)%s", settled, where)
        except Exception:
            logger.exception("Subscription settlement failed%s", where)
