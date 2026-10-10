# SPDX-License-Identifier: AGPL-3.0-or-later
"""Per-process cache of each user's session revocation watermark.

The UI guard asks on every page load whether the session in front of it was
revoked. Answering from the database each time would be a query per request;
answering from here is one per user per ``TTL_SECONDS``.

The bound that buys is the documented one: a bump made in *this* process is
seen at once (the bumping caller calls ``forget``), a bump made in another
process — a second replica, or ``kaleta reset-password`` from a shell — within
``TTL_SECONDS``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from kaleta.db.tenant_context import current_tenant
from kaleta.services.auth_service import AuthService
from kaleta.services.session import with_session

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

#: How long a watermark read from the database is trusted without asking again.
TTL_SECONDS = 60.0


@dataclass(frozen=True)
class _Entry:
    valid_from: datetime | None
    fetched_at: float


#: ``(tenant_id, user_id)``: every family's schema numbers its ``users`` from
#: 1, so a user id alone names several people. The family is ``None`` only for
#: code that runs outside one.
_Key = tuple[int | None, int]


def _key(user_id: int) -> _Key:
    ctx = current_tenant()
    return (ctx.tenant_id if ctx is not None else None, user_id)


class RevocationCache:
    """``(tenant, user_id) → (valid_from, fetched_at)``, refreshed after ``ttl_seconds``.

    The tenant is the one current when asked — the same one the database read
    behind a miss goes to.
    """

    def __init__(self, ttl_seconds: float = TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._entries: dict[_Key, _Entry] = {}

    async def valid_from(self, user_id: int) -> datetime | None:
        """The watermark for ``user_id``, from memory while it is fresh enough."""
        now = time.monotonic()
        key = _key(user_id)
        entry = self._entries.get(key)
        if entry is not None and now - entry.fetched_at < self._ttl:
            return entry.valid_from
        valid_from = await self._load(user_id)
        self._entries[key] = _Entry(valid_from, now)
        return valid_from

    def forget(self, user_id: int) -> None:
        """Drop the entry, so the next check reads the database."""
        self._entries.pop(_key(user_id), None)

    def clear(self) -> None:
        self._entries.clear()

    @staticmethod
    async def _load(user_id: int) -> datetime | None:
        async def _read(session: AsyncSession) -> datetime | None:
            return await AuthService(session).sessions_valid_from(user_id)

        return await with_session(_read)


revocation_cache = RevocationCache()
