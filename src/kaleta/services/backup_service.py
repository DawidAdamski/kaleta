from __future__ import annotations

import contextlib
import io
import json
import zipfile
from datetime import date, datetime
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession

_BACKUP_VERSION = "1"

# Order matters: export order respects FK dependencies (parents before children).
# Restore uses the same order with FK checks disabled.
_TABLES = [
    "institutions",
    "categories",
    "accounts",
    "assets",
    "budgets",
    "currency_rates",
    "transactions",
    "transaction_splits",
]


def _serialize(val: object) -> object:
    if isinstance(val, Decimal):
        return str(val)
    if isinstance(val, (date, datetime)):
        return val.isoformat()
    return val


class BackupService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def export(self) -> bytes:
        """Dump every table to JSON and package as a ZIP archive."""
        buf = io.BytesIO()
        meta: dict[str, Any] = {
            "version": _BACKUP_VERSION,
            "exported_at": datetime.utcnow().isoformat(),
            "tables": {},
        }

        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for table in _TABLES:
                # nosec B608: table names come only from the hardcoded _TABLES allowlist.
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
        Raises ValueError for invalid/incompatible backups.
        """
        with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
            names = zf.namelist()
            if "metadata.json" not in names:
                raise ValueError("Invalid backup: missing metadata.json")
            meta = json.loads(zf.read("metadata.json"))
            if str(meta.get("version")) != _BACKUP_VERSION:
                raise ValueError(
                    f"Unsupported backup version: {meta.get('version')} "
                    f"(expected {_BACKUP_VERSION})"
                )
            table_data: dict[str, list[dict[str, Any]]] = {}
            for table in _TABLES:
                fname = f"{table}.json"
                table_data[table] = json.loads(zf.read(fname)) if fname in names else []

        # Disable FK constraints for the duration of the restore (SQLite only; safe no-op on PG)
        with contextlib.suppress(Exception):
            await self.session.execute(text("PRAGMA foreign_keys = OFF"))

        try:
            # Clear tables in reverse dependency order
            for table in reversed(_TABLES):
                # nosec B608: table names come only from the hardcoded _TABLES allowlist.
                await self.session.execute(text(f"DELETE FROM {table}"))  # nosec B608

            # Build a map of known columns per table from the live schema.
            # run_sync is required because SQLAlchemy's inspect() is synchronous.
            conn = await self.session.connection()
            schema_cols: dict[str, set[str]] = {}
            for _t in _TABLES:

                def _column_names(sync_conn: Any, table_name: str = _t) -> set[str]:
                    return {
                        cast(str, col["name"]) for col in inspect(sync_conn).get_columns(table_name)
                    }

                schema_cols[_t] = await conn.run_sync(_column_names)

            counts: dict[str, int] = {}
            for table in _TABLES:
                rows = table_data.get(table, [])
                if rows:
                    allowed = schema_cols[table]
                    cols = [c for c in rows[0] if c in allowed]
                    if not cols:
                        counts[table] = 0
                        continue
                    col_names = ", ".join(cols)
                    placeholders = ", ".join(f":{c}" for c in cols)
                    stmt = text(
                        # nosec B608: table and column names are constrained by schema introspection.
                        f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})"  # nosec B608
                    )
                    for row in rows:
                        await self.session.execute(stmt, {c: row[c] for c in cols if c in row})
                counts[table] = len(rows)

            await self.session.commit()
            return counts
        except Exception:
            await self.session.rollback()
            raise
        finally:
            with contextlib.suppress(Exception):
                await self.session.execute(text("PRAGMA foreign_keys = ON"))
