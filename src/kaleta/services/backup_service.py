# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, date, datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from sqlalchemy import Date, DateTime, Numeric, insert, inspect, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.type_api import TypeEngine

import kaleta.models  # noqa: F401 — register every table on Base.metadata
from kaleta.db.base import Base
from kaleta.exceptions import ValidationError

_BACKUP_VERSION = "1"


async def _set_sqlite_foreign_keys(session: AsyncSession, *, enabled: bool) -> None:
    """Toggle SQLite FK enforcement. No-op on other dialects (avoids aborting PG txns)."""
    conn = await session.connection()
    if conn.dialect.name != "sqlite":
        return
    await session.execute(text(f"PRAGMA foreign_keys = {'ON' if enabled else 'OFF'}"))


@lru_cache(maxsize=1)
def _current_alembic_revision() -> str:
    """Return the alembic head revision for the installed code."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    alembic_ini = Path(__file__).resolve().parents[3] / "alembic.ini"
    cfg = Config(str(alembic_ini))
    script = ScriptDirectory.from_config(cfg)
    head = script.get_current_head()
    if head is None:
        raise ValidationError("No alembic head revision found")
    return head


def _backup_tables() -> list[str]:
    """ORM tables in FK-safe order — single source of truth for export/restore."""
    return [table.name for table in Base.metadata.sorted_tables]


def _serialize(val: object) -> object:
    if isinstance(val, Decimal):
        return str(val)
    if isinstance(val, (date, datetime)):
        return val.isoformat()
    return val


def _deserialize_value(val: object, col_type: TypeEngine[Any]) -> object:
    """Convert JSON-scalar values back to driver-friendly Python types (asyncpg-safe)."""
    if val is None:
        return None
    if isinstance(col_type, DateTime):
        if isinstance(val, str):
            parsed = datetime.fromisoformat(val)
            if not col_type.timezone and parsed.tzinfo is not None:
                return parsed.replace(tzinfo=None)
            return parsed
        return val
    if isinstance(col_type, Date):
        if isinstance(val, str):
            # Accept plain dates; tolerate accidental datetime ISO by taking the date part.
            return date.fromisoformat(val[:10])
        return val
    if isinstance(col_type, Numeric):
        if isinstance(val, Decimal):
            return val
        return Decimal(str(val))
    return val


def _deserialize_row(table_name: str, row: dict[str, Any]) -> dict[str, Any]:
    table = Base.metadata.tables[table_name]
    prepared: dict[str, Any] = {}
    for key, val in row.items():
        column = table.columns.get(key)
        if column is None:
            prepared[key] = val
            continue
        prepared[key] = _deserialize_value(val, column.type)
    return prepared


class BackupService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def export_filename() -> str:
        """Return a timestamped ZIP filename for backup downloads."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"kaleta_backup_{timestamp}.zip"

    async def export(self) -> bytes:
        """Dump every ORM table to JSON and package as a ZIP archive."""
        tables = _backup_tables()
        buf = io.BytesIO()
        meta: dict[str, Any] = {
            "version": _BACKUP_VERSION,
            "alembic_revision": _current_alembic_revision(),
            "exported_at": datetime.now(UTC).isoformat(),
            "tables": {},
        }

        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for table in tables:
                # nosec B608: table names come only from Base.metadata.sorted_tables.
                result = await self.session.execute(text(f"SELECT * FROM {table}"))  # nosec B608
                columns = list(result.keys())
                rows = [
                    {col: _serialize(val) for col, val in zip(columns, row, strict=False)}
                    for row in result.fetchall()
                ]
                meta["tables"][table] = len(rows)
                zf.writestr(f"{table}.json", json.dumps(rows, ensure_ascii=False, indent=2))

            zf.writestr("metadata.json", json.dumps(meta, ensure_ascii=False, indent=2))

        return buf.getvalue()

    async def restore(self, data: bytes) -> dict[str, int]:
        """Replace all data with the contents of a backup ZIP.

        Returns a mapping of table name → number of rows restored.
        Raises ValidationError for invalid/incompatible backups.
        """
        tables = _backup_tables()
        current_revision = _current_alembic_revision()

        with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
            names = zf.namelist()
            if "metadata.json" not in names:
                raise ValidationError("Invalid backup: missing metadata.json")
            meta = json.loads(zf.read("metadata.json"))
            if str(meta.get("version")) != _BACKUP_VERSION:
                raise ValidationError(
                    f"Unsupported backup version: {meta.get('version')} "
                    f"(expected {_BACKUP_VERSION})"
                )
            backup_revision = meta.get("alembic_revision")
            if not backup_revision:
                raise ValidationError(
                    "Backup is missing alembic_revision; refuse restore to avoid "
                    "silent data loss. Re-export from a current Kaleta version."
                )
            if str(backup_revision) != current_revision:
                raise ValidationError(
                    f"Backup schema revision {backup_revision!r} does not match "
                    f"this app ({current_revision!r}). Migrate the backup before "
                    "restoring (not yet supported)."
                )
            table_data: dict[str, list[dict[str, Any]]] = {}
            for table in tables:
                fname = f"{table}.json"
                table_data[table] = json.loads(zf.read(fname)) if fname in names else []

        # Disable FK constraints for the duration of the restore (SQLite only).
        # Do not run PRAGMA on PostgreSQL — a failed statement aborts the transaction.
        await _set_sqlite_foreign_keys(self.session, enabled=False)

        try:
            # Clear every ORM table so restore never leaves a hybrid state.
            for table in reversed(tables):
                # nosec B608: table names come only from Base.metadata.sorted_tables.
                await self.session.execute(text(f"DELETE FROM {table}"))  # nosec B608

            # Build a map of known columns per table from the live schema.
            # run_sync is required because SQLAlchemy's inspect() is synchronous.
            conn = await self.session.connection()
            schema_cols: dict[str, set[str]] = {}
            for _t in tables:

                def _column_names(sync_conn: Any, table_name: str = _t) -> set[str]:
                    return {
                        cast(str, col["name"]) for col in inspect(sync_conn).get_columns(table_name)
                    }

                schema_cols[_t] = await conn.run_sync(_column_names)

            counts: dict[str, int] = {}
            for table in tables:
                rows = table_data.get(table, [])
                if rows:
                    allowed = schema_cols[table]
                    for row in rows:
                        unknown = sorted(set(row) - allowed)
                        if unknown:
                            raise ValidationError(
                                f"Backup for {table} has unknown columns: {', '.join(unknown)}"
                            )
                    cols = list(rows[0].keys())
                    if not cols:
                        counts[table] = 0
                        continue
                    # Core insert applies dialect bind processors (Decimal/date/datetime).
                    table_obj = Base.metadata.tables[table]
                    payload = [
                        {c: prepared[c] for c in cols}
                        for prepared in (_deserialize_row(table, row) for row in rows)
                    ]
                    await self.session.execute(insert(table_obj), payload)
                counts[table] = len(rows)

            await self.session.commit()
            return counts
        except Exception:
            await self.session.rollback()
            raise
        finally:
            await _set_sqlite_foreign_keys(self.session, enabled=True)
