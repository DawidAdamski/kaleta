# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ordering by user text, in Python (``hosted-field-encryption``).

Names and descriptions are ``EncryptedText``: ciphertext with encryption on,
format-prefixed bytes with it off. Either way SQL ``ORDER BY name`` sorts
bytes, not words, so every list ordered by a name is fetched unordered and
sorted here — case-insensitively, the order a person expects.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol


class _Named(Protocol):
    @property
    def name(self) -> str: ...


def text_key(value: str | None) -> str:
    """The sort key of a piece of user text; ``None`` sorts first."""
    return "" if value is None else value.casefold()


def by_name[NamedT: _Named](items: Iterable[NamedT]) -> list[NamedT]:
    """``items`` ordered by ``name`` (case-insensitive), stable for equal names."""
    return sorted(items, key=lambda item: text_key(item.name))
