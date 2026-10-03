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
from itertools import chain
from typing import Any

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

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
