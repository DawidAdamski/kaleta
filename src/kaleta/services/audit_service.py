from __future__ import annotations

import json

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.db.base import Base
from kaleta.models.audit_log import MAX_AUDIT_ENTRIES, AuditLog


class AuditService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, limit: int = MAX_AUDIT_ENTRIES) -> list[AuditLog]:
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

    async def revert(self, audit_id: int) -> None:
        entry = await self.session.get(AuditLog, audit_id)
        if entry is None or entry.reverted:
            return

        table = Base.metadata.tables.get(entry.table_name)
        if table is None:
            raise ValueError(f"Unknown table: {entry.table_name!r}")

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
