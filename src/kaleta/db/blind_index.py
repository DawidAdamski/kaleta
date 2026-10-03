# SPDX-License-Identifier: AGPL-3.0-or-later
"""Keep every ``*_bidx`` column in step with the encrypted column it indexes.

A model declares ``__blind_indexes__ = {"name_bidx": ("name", blind_index)}``;
before every flush, each new object, and each dirty one whose source attribute
changed, gets its index recomputed under the current data key. Services never
set a ``_bidx`` themselves, so none can forget to.

What this does not see is a bulk ``update(Model).values(name=…)``: such a
statement has to set the ``_bidx`` column itself (there are none today — keep
it that way, or add the column to the ``values``).
"""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache
from itertools import chain
from typing import Any

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from kaleta.db.base import Base

BlindIndexFn = Callable[[str | None], str | None]
#: ``{"<target>_bidx": ("<source attribute>", index function)}``
BlindIndexSpec = dict[str, tuple[str, BlindIndexFn]]


def _fill_blind_indexes(session: Session, _flush_context: Any, _instances: Any) -> None:
    new = set(map(id, session.new))
    for obj in chain(session.new, session.dirty):
        spec: BlindIndexSpec | None = getattr(type(obj), "__blind_indexes__", None)
        if not spec:
            continue
        state = inspect(obj)
        for target, (source, index) in spec.items():
            if id(obj) in new or state.attrs[source].history.has_changes():
                setattr(obj, target, index(getattr(obj, source)))


event.listen(Session, "before_flush", _fill_blind_indexes)


@lru_cache(maxsize=1)
def blind_index_specs() -> dict[str, BlindIndexSpec]:
    """``{table: __blind_indexes__}`` of every mapped class that declares them.

    For code that writes rows without the ORM — a backup restore, the
    re-encryption of a database — where the flush hook above does not run.
    """
    specs: dict[str, BlindIndexSpec] = {}
    for mapper in Base.registry.mappers:
        spec: BlindIndexSpec | None = getattr(mapper.class_, "__blind_indexes__", None)
        if spec:
            for table in mapper.tables:
                specs[table.name] = spec
    return specs


def with_blind_indexes(table_name: str, row: dict[str, Any]) -> dict[str, Any]:
    """``row`` with every blind index of ``table_name`` recomputed from its plaintext.

    Under the current key: a row written under another one (or under the
    plaintext-mode key) gets the index this install will look it up by.
    """
    spec = blind_index_specs().get(table_name)
    if not spec:
        return row
    for target, (source, index) in spec.items():
        if source in row:
            row[target] = index(row[source])
    return row
