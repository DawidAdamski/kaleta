# SPDX-License-Identifier: AGPL-3.0-or-later
"""Opt-in NBP Table A fetch when the NiceGUI / API process starts."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.config.setup_config import get_db_url, get_nbp_fetch_on_startup
from kaleta.exceptions import ExternalServiceError, KaletaError
from kaleta.services.nbp_rate_service import NbpRateService
from kaleta.services.session import with_session

logger = logging.getLogger(__name__)


class NbpStartupFetcher:
    """Fire-and-forget startup import when the user opted in (default OFF)."""

    _task: asyncio.Task[None] | None = None

    @classmethod
    def start(cls) -> None:
        """Schedule a single fetch when opt-in is enabled and a DB is configured."""
        if not get_nbp_fetch_on_startup():
            logger.debug("NBP fetch on startup skipped (opt-in off)")
            return
        if not get_db_url():
            logger.debug("NBP fetch on startup skipped (database not configured)")
            return
        if cls._task is not None and not cls._task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("NBP fetch on startup skipped: no running event loop")
            return
        cls._task = loop.create_task(cls._run_once(), name="kaleta-nbp-startup-fetch")
        logger.info("NBP Table A fetch scheduled on startup")

    @classmethod
    async def stop(cls) -> None:
        """Cancel an in-flight startup fetch (process shutdown)."""
        task = cls._task
        cls._task = None
        if task is None:
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    @classmethod
    async def _run_once(cls) -> None:
        try:

            async def _import(session: AsyncSession) -> None:
                await NbpRateService(session).import_latest()

            await with_session(_import)
        except ExternalServiceError as exc:
            logger.warning("NBP fetch on startup failed soft: %s", exc.message)
        except KaletaError as exc:
            logger.warning("NBP fetch on startup rejected: %s", exc.message)
        except Exception:
            logger.exception("NBP fetch on startup failed unexpectedly")
