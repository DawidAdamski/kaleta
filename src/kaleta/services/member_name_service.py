# SPDX-License-Identifier: AGPL-3.0-or-later
"""What the household calls each of its members (``hosted-household-sharing`` §4).

Attribution columns (``user_id`` on user-owned rows and on ``audit_log``) point
at the family's own ``users`` rows. This turns them into names, by the same
rule the Household tab uses (:meth:`MemberNameService.name`). A removed member
keeps their row, so what they did keeps their name.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.user import User

#: From this many members on, a family is a household and the pages say who did what.
HOUSEHOLD_SIZE = 2


class MemberNameService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def names(self) -> dict[int, str]:
        """Every member's name by their ``users.id``, in the order they joined."""
        rows = await self.session.execute(
            select(User.id, User.display_name, User.email, User.username).order_by(User.id)
        )
        return {
            user_id: self.name(display_name, email or username)
            for user_id, display_name, email, username in rows.all()
        }

    @staticmethod
    def name(display_name: str | None, email: str) -> str:
        """The name they chose, else the part of their e-mail before the ``@``."""
        return display_name or email.split("@", 1)[0]

    @staticmethod
    def is_household(names: dict[int, str]) -> bool:
        """Whether there is more than one person to tell apart."""
        return len(names) >= HOUSEHOLD_SIZE
