# SPDX-License-Identifier: AGPL-3.0-or-later
"""Session-start auto-post of due planned transactions."""

from __future__ import annotations

import logging
from typing import Any

from nicegui import app, ui

from kaleta.auth.session import is_authenticated
from kaleta.exceptions import KaletaError
from kaleta.i18n import t
from kaleta.services import PlannedTransactionService, with_session
from kaleta.views.error_handling import notify_kaleta_error
from kaleta.views.settings.constants import (
    DEFAULT_AUTO_POST_DUE_ON_STARTUP,
    DEFAULT_PAYMENT_CALENDAR_OVERDUE_DAYS,
)

logger = logging.getLogger(__name__)

_SESSION_FLAG = "_auto_post_due_ran"


async def maybe_auto_post_due() -> None:
    """Run ``post_due`` once per authenticated session when the Features toggle is on.

    NiceGUI ``app.storage.user`` is unavailable in process ``on_startup``, so the
    equivalent hook is the first authenticated ``page_layout`` of the session.
    """
    if not is_authenticated():
        return
    if app.storage.user.get(_SESSION_FLAG):
        return
    enabled = bool(
        app.storage.user.get("auto_post_due_on_startup", DEFAULT_AUTO_POST_DUE_ON_STARTUP)
    )
    # Mark before awaiting so concurrent page loads do not double-run.
    app.storage.user[_SESSION_FLAG] = True
    if not enabled:
        return

    lookback = (
        int(app.storage.user.get("payment_calendar_overdue_days", 0) or 0)
        or DEFAULT_PAYMENT_CALENDAR_OVERDUE_DAYS
    )

    try:

        async def _run(session: Any) -> int:
            posted = await PlannedTransactionService(session).post_due(lookback_days=lookback)
            return len(posted)

        count = await with_session(_run)
    except KaletaError as exc:
        notify_kaleta_error(exc)
        return
    except Exception:
        logger.exception("Auto-post due planned transactions failed")
        return

    if count > 0:
        ui.notify(t("planned.auto_posted", count=count), type="positive")
