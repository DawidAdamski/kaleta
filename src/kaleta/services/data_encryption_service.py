# SPDX-License-Identifier: AGPL-3.0-or-later
"""Rewrite every user-text column under the current key (``hosted-field-encryption``).

The migration leaves an existing database in plaintext format (``\\x00``) with
its blind indexes under the plaintext-mode key. Switching encryption on is
then one pass over every ``EncryptedText``/``EncryptedJSON`` column: read each
value (either format decodes), write it back (the column type encrypts under
the data key bound to this context) and recompute every blind index from the
plaintext, since an index under the old key matches nothing under the new.

The same pass runs the other way for ``scripts/encrypt_database.py
--decrypt``: read under the key, write with encryption switched off.

What it cannot recompute is ``dismissed_candidate_patterns.merchant_key``,
which stores only an index, never the merchant name: those dismissals stop
matching and the candidates they hid are offered again.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import Table, bindparam, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.db.base import Base
from kaleta.db.blind_index import blind_index_specs, with_blind_indexes
from kaleta.db.types import EncryptedJSON, EncryptedText

log = logging.getLogger(__name__)

#: Rows per ``executemany``: big enough to amortise the round trip, small
#: enough that a 50 000-row ledger never sits in one statement.
_BATCH = 1000


def _encrypted_columns(table: Table) -> list[str]:
    return [
        col.name for col in table.columns if isinstance(col.type, (EncryptedText, EncryptedJSON))
    ]


class DataEncryptionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def rewrite_all(self) -> dict[str, int]:
        """Rewrite every encrypted column and blind index; return rows per table.

        Does not commit — the caller decides whether the whole pass lands.
        """
        counts: dict[str, int] = {}
        for table in Base.metadata.sorted_tables:
            columns = _encrypted_columns(table)
            if not columns:
                continue
            counts[table.name] = await self._rewrite_table(table, columns)
        return counts

    async def _rewrite_table(self, table: Table, columns: list[str]) -> int:
        keys = [col.name for col in table.primary_key.columns]
        spec = blind_index_specs().get(table.name, {})
        targets = [target for target in spec if target not in columns]
        result = await self.session.execute(
            select(*(table.c[name] for name in [*keys, *columns])).order_by(
                *(table.c[name] for name in keys)
            )
        )
        rows = [dict(row._mapping) for row in result]
        if not rows:
            return 0
        written = [*columns, *targets]
        stmt = (
            update(table)
            .where(*(table.c[name] == bindparam(f"pk_{name}") for name in keys))
            .values({name: bindparam(f"v_{name}") for name in written})
        )
        for start in range(0, len(rows), _BATCH):
            batch: list[dict[str, Any]] = []
            for row in rows[start : start + _BATCH]:
                indexed = with_blind_indexes(table.name, dict(row))
                params = {f"pk_{name}": row[name] for name in keys}
                params.update({f"v_{name}": indexed.get(name) for name in written})
                batch.append(params)
            await self.session.execute(stmt, batch)
        log.info("Rewrote %d rows of %s", len(rows), table.name)
        return len(rows)
