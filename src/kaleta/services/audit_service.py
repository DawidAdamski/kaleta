# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.db.base import Base
from kaleta.exceptions import NotFoundError
from kaleta.models.audit_log import MAX_AUDIT_ENTRIES, AuditLog


@dataclass(frozen=True)
class AuditEntryDisplay:
    """Audit log row prepared for the settings history tab."""

    id: int
    timestamp: datetime
    operation: str
    table_name: str
    record_id: int | None
    reverted: bool
    changed_fields: tuple[str, ...]
    #: The member who made the change; ``None`` when nobody is recorded.
    user_id: int | None = None


class AuditService:
    MAX_ENTRIES = MAX_AUDIT_ENTRIES

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_entries(self, limit: int = MAX_AUDIT_ENTRIES) -> list[AuditLog]:
        result = await self.session.execute(
            select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
        )
        entries = list(result.scalars())

        # Trim: if we filled the limit, older entries exist — delete them now.
        if len(entries) == limit:
            oldest_kept_id = entries[-1].id
            await self.session.execute(delete(AuditLog).where(AuditLog.id < oldest_kept_id))
            await self.session.commit()

        return entries

    async def list_for_display(self, limit: int = MAX_AUDIT_ENTRIES) -> list[AuditEntryDisplay]:
        """Return audit entries with parsed change metadata for UI rendering."""
        entries = await self.list_entries(limit)
        return [self._to_display(entry) for entry in entries]

    @staticmethod
    def changed_field_names(entry: AuditLog) -> tuple[str, ...]:
        """Parse UPDATE ``old_data`` JSON and return changed field names."""
        if entry.operation != "UPDATE":
            return ()
        try:
            keys = list(json.loads(entry.old_data or "{}").keys())
        except json.JSONDecodeError:
            return ()
        return tuple(keys)

    @classmethod
    def _to_display(cls, entry: AuditLog) -> AuditEntryDisplay:
        return AuditEntryDisplay(
            id=entry.id,
            timestamp=entry.timestamp,
            operation=entry.operation,
            table_name=entry.table_name,
            record_id=entry.record_id,
            reverted=entry.reverted,
            changed_fields=cls.changed_field_names(entry),
            user_id=entry.user_id,
        )

    async def last_changed_by(self, table_name: str, record_id: int) -> int | None:
        """The member behind the newest recorded change of one row, if anyone is recorded."""
        result = await self.session.execute(
            select(AuditLog.user_id)
            .where(AuditLog.table_name == table_name, AuditLog.record_id == record_id)
            .order_by(AuditLog.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def revert(self, audit_id: int) -> None:
        entry = await self.session.get(AuditLog, audit_id)
        if entry is None or entry.reverted:
            return

        table = Base.metadata.tables.get(entry.table_name)
        if table is None:
            raise NotFoundError(f"Unknown table: {entry.table_name!r}")

        if entry.operation == "INSERT":
            # Revert: delete the record that was inserted
            await self.session.execute(delete(table).where(table.c.id == entry.record_id))
        elif entry.operation == "DELETE":
            # Revert: re-insert the deleted record with its original data
            data = json.loads(entry.old_data or "{}")
            await self.session.execute(table.insert().values(**data))
        elif entry.operation == "UPDATE":
            # Revert: restore the old field values
            data = json.loads(entry.old_data or "{}")
            if data and entry.record_id is not None:
                await self.session.execute(
                    table.update().where(table.c.id == entry.record_id).values(**data)
                )

        entry.reverted = True
        await self.session.commit()

    async def clear(self) -> None:
        await self.session.execute(delete(AuditLog))
        await self.session.commit()
