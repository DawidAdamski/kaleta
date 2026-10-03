# SPDX-License-Identifier: AGPL-3.0-or-later
"""The data-passphrase gate: a signed-in but locked browser goes to ``/unlock``.

Covers: KAL-ENC-003, KAL-ENC-007
"""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
from nicegui.storage import request_contextvar

from kaleta.auth import session as session_mod
from kaleta.config import settings
from kaleta.crypto import key_ring, local_member_ref
from kaleta.exceptions import TenantLockedError
from tests.conftest import TEST_DATA_KEY
from tests.unit.auth.test_session_ttl import (  # noqa: F401 — fixtures
    _ago,
    auth_middleware_client,
    fake_storage,
    idle_12_ttl_72,
)

BROWSER = "browser-1"


@pytest.fixture
def locked_browser(
    fake_storage: dict[str, Any],  # noqa: F811 — the imported fixture
    monkeypatch: pytest.MonkeyPatch,
    real_unlock: None,
) -> Iterator[dict[str, Any]]:
    """Encryption on; a signed-in user 1 whose browser has unlocked nothing yet."""
    monkeypatch.setattr(settings, "encryption", "passphrase")
    key_ring.clear()
    token = request_contextvar.set(SimpleNamespace(session={"id": BROWSER}))  # type: ignore[arg-type]
    fake_storage[session_mod.SESSION_AUTHENTICATED] = True
    fake_storage[session_mod.SESSION_USER_ID] = 1
    fake_storage[session_mod.SESSION_LOGIN_AT] = _ago(minutes=5)
    fake_storage[session_mod.SESSION_LAST_SEEN_AT] = _ago(minutes=1)
    yield fake_storage
    request_contextvar.reset(token)
    key_ring.clear()


def test_a_session_is_unlocked_only_by_its_own_member(locked_browser: dict[str, Any]) -> None:
    assert not session_mod.is_unlocked()

    key_ring.put(BROWSER, TEST_DATA_KEY, member_ref=local_member_ref(2))
    assert not session_mod.is_unlocked()

    key_ring.put(BROWSER, TEST_DATA_KEY, member_ref=local_member_ref(1))
    assert session_mod.is_unlocked()
    assert session_mod.session_data_key() == TEST_DATA_KEY


def test_signing_out_locks(locked_browser: dict[str, Any]) -> None:
    """Covers: KAL-ENC-007"""
    key_ring.put(BROWSER, TEST_DATA_KEY, member_ref=local_member_ref(1))

    session_mod.logout_session()

    assert key_ring.get(BROWSER) is None


@pytest.mark.usefixtures("idle_12_ttl_72")
async def test_a_locked_page_load_goes_to_unlock(
    locked_browser: dict[str, Any],
    auth_middleware_client: httpx.AsyncClient,  # noqa: F811 — the imported fixture
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers: KAL-ENC-003"""
    from kaleta.auth import middleware as middleware_mod

    async def _not_revoked() -> bool:
        return False

    # A signed-in user id sends the guard to the revocation watermark in the
    # database, which this unit test has none of; revocation has its own
    # tests (test_session_revocation.py) — here it is the unlock step alone.
    monkeypatch.setattr(middleware_mod, "current_session_revoked", _not_revoked)
    locked = await auth_middleware_client.get("/transactions")
    assert locked.status_code == 307
    assert locked.headers["location"] == "/unlock?redirect_to=/transactions"

    key_ring.put(BROWSER, TEST_DATA_KEY, member_ref=local_member_ref(1))
    unlocked = await auth_middleware_client.get("/transactions")
    assert unlocked.status_code == 200


@pytest.mark.usefixtures("idle_12_ttl_72")
async def test_the_api_cookie_path_answers_423_while_locked(
    locked_browser: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Covers: KAL-ENC-007"""
    from kaleta.api import deps

    async def _one(_request: object) -> int:
        return 1

    monkeypatch.setattr(deps, "authenticated_user_id", _one)
    request = MagicMock(method="GET")

    with pytest.raises(TenantLockedError):
        await deps.get_current_user_id(request, None, MagicMock())

    key_ring.put(BROWSER, TEST_DATA_KEY, member_ref=local_member_ref(1))
    assert await deps.get_current_user_id(request, None, MagicMock()) == 1
