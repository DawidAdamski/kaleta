# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.user import User


class AuthService:
    """A member's sessions in their family: the revocation watermark and the audit trail.

    Passwords are not here: a login's credential lives in the registry
    (``LocalIdentityService``) or with the identity provider (ADR-38).
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def revoke_sessions(self, user_id: int, *, commit: bool = True) -> datetime:
        """End every session ``user_id`` signed in to before now; return the watermark.

        Nothing is deleted: sessions are files keyed by browser, with no index
        from a user to them. The guards compare each session's sign-in time
        with this watermark instead. ``commit=False`` lets a credential change
        bump it in its own transaction.

        Callers in a UI process should also forget the cached watermark (see
        ``kaleta.auth.revocation_cache``) — this layer cannot reach it.
        """
        now = datetime.now(UTC)
        await self.session.execute(
            update(User).where(User.id == user_id).values(sessions_valid_from=now)
        )
        if commit:
            await self.session.commit()
        return now

    async def sessions_valid_from(self, user_id: int) -> datetime | None:
        """The revocation watermark for ``user_id``, in UTC; ``None`` if never bumped."""
        result = await self.session.execute(
            select(User.sessions_valid_from).where(User.id == user_id)
        )
        stamp = result.scalar_one_or_none()
        if stamp is None:
            return None
        # SQLite hands back naive datetimes even for a timezone-aware column.
        return stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC)

    async def record_login(self, *, username: str | None, success: bool) -> None:
        from kaleta.db.audit import record_auth_event

        await record_auth_event(
            self.session,
            event="login",
            username=username,
            success=success,
        )

    async def record_logout(self, *, username: str | None) -> None:
        from kaleta.db.audit import record_auth_event

        await record_auth_event(
            self.session,
            event="logout",
            username=username,
            success=True,
        )
