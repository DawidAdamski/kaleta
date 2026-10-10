# SPDX-License-Identifier: AGPL-3.0-or-later
"""The instance's NBP fetch: at start-up and once a day, when ``KALETA_NBP_FETCH`` is on.

One fetch for every family — the rates land in ``public.nbp_rates``
(ADR-38, part B2c). Off by default (KAL-FXR-003). A failed fetch is logged
and waits for the next day; the app never depends on NBP being reachable.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from kaleta.config import settings
from kaleta.db import AsyncSessionFactory
from kaleta.exceptions import ExternalServiceError, KaletaError
from kaleta.services.nbp_rate_service import NbpRateService

logger = logging.getLogger(__name__)

_FETCH_INTERVAL_SECONDS = 24 * 3600


class NbpRateScheduler:
    """Fetch NBP Table A on start-up and every 24 hours."""

    _task: asyncio.Task[None] | None = None

    @classmethod
    def start(cls) -> None:
        if not settings.nbp_fetch:
            logger.debug("NBP fetch not scheduled (KALETA_NBP_FETCH is off)")
            return
        if cls._task is not None and not cls._task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("NBP fetch not scheduled: no running event loop")
            return
        cls._task = loop.create_task(cls._loop(), name="kaleta-nbp-fetch")
        logger.info("NBP Table A fetch scheduled: now and once a day")

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
        while True:
            await cls.fetch_once()
            await asyncio.sleep(_FETCH_INTERVAL_SECONDS)

    @classmethod
    async def fetch_once(cls) -> None:
        """One fetch; whatever goes wrong is logged, never raised."""
        try:
            async with AsyncSessionFactory.public() as public:
                await NbpRateService(public).import_latest()
        except ExternalServiceError as exc:
            logger.warning("NBP fetch failed soft: %s", exc.message)
        except KaletaError as exc:
            logger.warning("NBP fetch rejected: %s", exc.message)
        except Exception:
            logger.exception("NBP fetch failed unexpectedly")
