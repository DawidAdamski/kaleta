# SPDX-License-Identifier: AGPL-3.0-or-later
"""``kaleta.auth.household``: whoever loses access is forgotten by this process too.

The service revokes in the database; the revocation cache and the key ring of
this process are the auth layer's, and :mod:`kaleta.auth.household` drops them
after a removal and after leaving.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from kaleta.auth import household
from kaleta.crypto import DataKey
from kaleta.services.household_service import RemovedMember
from kaleta.services.instance_admin_service import RevokedMember

KEY = DataKey(b"\x01" * 32, version=1)
GONE = RemovedMember(tenant_id=7, user_id=3, rekeyed=True)


class _Service:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    async def remove(self, member_id: int, key: DataKey | None, *, rekey: bool) -> RemovedMember:
        self.calls.append(("remove", (member_id, key, rekey)))
        return GONE

    async def leave(self, key: DataKey | None) -> RemovedMember:
        self.calls.append(("leave", key))
        return GONE


@pytest.fixture
def wired(monkeypatch: pytest.MonkeyPatch) -> tuple[_Service, list[RevokedMember]]:
    service = _Service()
    forgotten: list[RevokedMember] = []

    async def _with(fn: Callable[[_Service], Awaitable[Any]]) -> Any:
        return await fn(service)

    monkeypatch.setattr(household, "with_household", _with)
    monkeypatch.setattr(household, "session_data_key", lambda: KEY)
    monkeypatch.setattr(household, "forget_revoked_member", lambda r: forgotten.append(r) or 1)
    return service, forgotten


async def test_removing_a_member_forgets_them_here(
    wired: tuple[_Service, list[RevokedMember]],
) -> None:
    service, forgotten = wired
    assert await household.remove_member(5, rekey=False) == GONE
    assert service.calls == [("remove", (5, KEY, False))]
    assert forgotten == [RevokedMember(tenant_id=7, user_id=3)]


async def test_leaving_forgets_the_member_who_left(
    wired: tuple[_Service, list[RevokedMember]],
) -> None:
    service, forgotten = wired
    await household.leave_household()
    assert service.calls == [("leave", KEY)]
    assert forgotten == [RevokedMember(tenant_id=7, user_id=3)]
