# SPDX-License-Identifier: AGPL-3.0-or-later
"""Two replicas, one Redis: the login lock is shared.

Each "replica" builds its limiter the way the app does at import —
``default_store("login")`` with ``KALETA_REDIS_URL`` set — and connects
lazily through ``Redis.from_url``. Against the server at ``KALETA_REDIS_URL``
when that is set (the CI ``redis`` job); otherwise ``from_url`` hands out
clients of one in-process fakeredis server, which is what two processes
pointed at one Redis see.

Covers: KAL-AUTH-034
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Generator
from typing import Any

import fakeredis
import pytest
from redis import Redis

from kaleta.auth import login_rate_limit as limit_mod
from kaleta.auth.login_rate_limit import LoginRateLimiter, RedisStore

_FALLBACK_URL = "redis://fake-shared-redis:6379/0"


@pytest.fixture
def namespace(monkeypatch: pytest.MonkeyPatch) -> Generator[str]:
    """Point settings at Redis; give this test a namespace of its own."""
    url = os.environ.get("KALETA_REDIS_URL")
    if url is None:
        server = fakeredis.FakeServer()

        def _from_url(_url: str, **_kwargs: Any) -> Redis:
            return fakeredis.FakeRedis(server=server)

        monkeypatch.setattr(Redis, "from_url", staticmethod(_from_url))
    monkeypatch.setattr(limit_mod.settings, "redis_url", url or _FALLBACK_URL)
    ns = f"it-{uuid.uuid4().hex}"
    yield ns
    if url is not None:
        client = Redis.from_url(url)
        keys = list(client.scan_iter(match=f"kaleta:{ns}:*"))
        if keys:
            client.delete(*keys)
        client.close()


def _replica(namespace: str) -> LoginRateLimiter:
    store = limit_mod.default_store(namespace)
    assert isinstance(store, RedisStore)
    return LoginRateLimiter(max_failures=5, window_seconds=15 * 60, store=store)


def test_five_failures_on_one_replica_lock_the_other(namespace: str) -> None:
    """Covers: KAL-AUTH-034"""
    first, second = _replica(namespace), _replica(namespace)
    address = "198.51.100.23"
    for attempt in range(1, 6):
        assert first.record_failure(address) is (attempt == 5)
    assert second.is_locked(address) is True
    assert 895 <= second.remaining_lock_seconds(address) <= 900


def test_failures_split_between_replicas_add_up(namespace: str) -> None:
    """Covers: KAL-AUTH-034"""
    first, second = _replica(namespace), _replica(namespace)
    address = "198.51.100.24"
    for replica in (first, second, first, second):
        assert replica.record_failure(address) is False
    assert second.record_failure(address) is True
    assert first.is_locked(address) is True
