# SPDX-License-Identifier: AGPL-3.0-or-later
"""The three counts the login page's right panel carries (artboard 3f).

Counts only — how many transactions, how many accounts, how many months the
ledger spans. Never an amount, never a name: the panel is read before anyone
has proved who they are, so it may say how much work is in here and nothing
about what the work says.
"""

from __future__ import annotations

import datetime
import logging
import time
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.account import Account
from kaleta.models.transaction import Transaction

logger = logging.getLogger(__name__)

#: Whether the login panel shows the counts at all. A single-user
#: self-hosted app has no one to hide them from; a public demo instance
#: might, and this is the one line to change.
AUTH_PANEL_STATS = True

#: The login page is hit by every unauthenticated request, including bots.
#: Three counts do not change second to second, so one minute of staleness
#: buys a page that costs nothing to serve.
_CACHE_SECONDS = 60.0


@dataclass(frozen=True, slots=True)
class AuthLandingStats:
    """What the panel may say. Zero counts are a fine thing to say."""

    transactions: int
    accounts: int
    months: int


#: (read at, counts) — the counts may be ``None``, which is a cached answer
#: too: a database that is not there will not be there a second later either,
#: and re-asking on every hit of an unauthenticated page is how a broken
#: install turns into a log full of the same warning.
_cache: tuple[float, AuthLandingStats | None] | None = None


def reset_auth_stats_cache() -> None:
    """Forget the cached counts — for tests, and for anything that reseeds."""
    global _cache
    _cache = None


class AuthStatsService:
    """Read-only counts for the pre-login panel."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def landing_stats(self) -> AuthLandingStats | None:
        """The three counts, or ``None`` when there is nothing to count yet.

        ``None`` also covers a database that is not there or not migrated:
        the panel then shows its line of copy alone rather than a login page
        that fails to render because the app has not been set up.
        """
        global _cache
        if not AUTH_PANEL_STATS:
            return None
        now = time.monotonic()
        if _cache is not None and now - _cache[0] < _CACHE_SECONDS:
            return _cache[1]

        stats: AuthLandingStats | None
        try:
            stats = await self._read()
        except Exception:  # noqa: BLE001 — a login page must render regardless
            # Warning, not debug: before setup this is expected and harmless,
            # but a broken query here looks exactly the same from outside, and
            # a panel that quietly shows nothing forever is not a thing anyone
            # would go looking for. Once per cache window, not per request.
            logger.warning("Login panel stats unavailable", exc_info=True)
            stats = None

        _cache = (now, stats)
        return stats

    async def _read(self) -> AuthLandingStats:
        transactions = await self.session.scalar(select(func.count()).select_from(Transaction))
        accounts = await self.session.scalar(select(func.count()).select_from(Account))
        first, last = (
            await self.session.execute(
                select(func.min(Transaction.date), func.max(Transaction.date))
            )
        ).one()
        return AuthLandingStats(
            transactions=int(transactions or 0),
            accounts=int(accounts or 0),
            months=months_between(first, last),
        )


def months_between(first: datetime.date | None, last: datetime.date | None) -> int:
    """Whole months the ledger covers, counting both ends.

    January to January is one month of history, not zero — the ledger has
    something in it, and a "0 months" panel beside a transaction count would
    contradict itself. An empty ledger has no ends and so no months.
    """
    if first is None or last is None:
        return 0
    return (last.year - first.year) * 12 + (last.month - first.month) + 1
