# SPDX-License-Identifier: AGPL-3.0-or-later
"""SQLite foreign-key integrity checks for Housekeeping."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import ValidationError


@dataclass(frozen=True, slots=True)
class ForeignKeyViolation:
    """One row returned by ``PRAGMA foreign_key_check``."""

    table: str
    rowid: int
    parent: str
    fkid: int


class IntegrityService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def is_sqlite(self) -> bool:
        conn = await self.session.connection()
        return conn.dialect.name == "sqlite"

    async def foreign_key_check(self) -> list[ForeignKeyViolation]:
        """Return orphan FK rows. Raises ValidationError on non-SQLite dialects."""
        if not await self.is_sqlite():
            raise ValidationError("Foreign-key integrity check is only available for SQLite")

        result = await self.session.execute(text("PRAGMA foreign_key_check"))
        violations: list[ForeignKeyViolation] = []
        for row in result.fetchall():
            violations.append(
                ForeignKeyViolation(
                    table=str(row[0]),
                    rowid=int(row[1]),
                    parent=str(row[2]),
                    fkid=int(row[3]),
                )
            )
        return violations
