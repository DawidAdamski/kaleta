# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for LoginRateLimiter and its two stores.

Every behaviour test runs once per store. The Redis store talks to the server
at ``KALETA_REDIS_URL`` when that is set (the CI ``valkey`` job, or a local
``redis://localhost:6379/0``), and to an in-process fakeredis server otherwise,
so the Redis code path is exercised on every run.

Covers: KAL-AUTH-008, KAL-AUTH-034
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable, Generator

import fakeredis
import pytest
from redis import Redis

from kaleta.auth import login_rate_limit as limit_mod
from kaleta.auth.login_rate_limit import (
    AttemptStore,
    LoginRateLimiter,
    MemoryStore,
    RedisStore,
)

#: Builds a Redis client; every client from one factory talks to one server,
#: the way two replicas share one Redis.
RedisClientFactory = Callable[[], "Redis"]


@pytest.fixture
def redis_clients() -> Generator[RedisClientFactory]:
    url = os.environ.get("KALETA_REDIS_URL")
    clients: list[Redis] = []
    if url:

        def make() -> Redis:
            client = Redis.from_url(url)
            clients.append(client)
            return client

    else:
        server = fakeredis.FakeServer()

        def make() -> Redis:
            client = fakeredis.FakeRedis(server=server)
            clients.append(client)
            return client

    yield make
    for client in clients:
        client.close()


@pytest.fixture
def namespace(redis_clients: RedisClientFactory) -> Generator[str]:
    """A namespace of its own per test, removed afterwards on a real server."""
    ns = f"test-{uuid.uuid4().hex}"
    yield ns
    client = redis_clients()
    keys = list(client.scan_iter(match=f"{limit_mod.REDIS_KEY_PREFIX}{ns}:*"))
    if keys:
        client.delete(*keys)


StoreFactory = Callable[[], AttemptStore]


@pytest.fixture(params=["memory", "redis"])
def new_store(
    request: pytest.FixtureRequest, redis_clients: RedisClientFactory, namespace: str
) -> StoreFactory:
    """A factory of stores that share state, like two replicas behind one backend."""
    if request.param == "memory":
        shared = MemoryStore()
        return lambda: shared
    return lambda: RedisStore(namespace, client=redis_clients())


class TestLoginRateLimiter:
    def test_locks_after_max_failures(self, new_store: StoreFactory) -> None:
        """Covers: KAL-AUTH-008"""
        limiter = LoginRateLimiter(max_failures=5, window_seconds=900, store=new_store())
        now = 1000.0
        for _ in range(4):
            assert limiter.record_failure("127.0.0.1", now=now) is False
            assert limiter.is_locked("127.0.0.1", now=now) is False
        assert limiter.record_failure("127.0.0.1", now=now) is True
        assert limiter.is_locked("127.0.0.1", now=now) is True
        assert limiter.remaining_lock_seconds("127.0.0.1", now=now) == 900

    def test_clear_unlocks(self, new_store: StoreFactory) -> None:
        limiter = LoginRateLimiter(max_failures=2, window_seconds=60, store=new_store())
        now = 50.0
        limiter.record_failure("a", now=now)
        limiter.record_failure("a", now=now)
        assert limiter.is_locked("a", now=now)
        limiter.clear("a")
        assert limiter.is_locked("a", now=now) is False

    def test_lock_expires(self, new_store: StoreFactory) -> None:
        limiter = LoginRateLimiter(max_failures=1, window_seconds=10, store=new_store())
        limiter.record_failure("b", now=0.0)
        assert limiter.is_locked("b", now=5.0)
        assert limiter.is_locked("b", now=10.0) is False

    def test_failures_while_locked_do_not_extend_the_lock(self, new_store: StoreFactory) -> None:
        limiter = LoginRateLimiter(max_failures=2, window_seconds=60, store=new_store())
        limiter.record_failure("c", now=0.0)
        limiter.record_failure("c", now=0.0)
        assert limiter.record_failure("c", now=30.0) is True
        assert limiter.remaining_lock_seconds("c", now=30.0) == 30

    def test_a_fresh_count_starts_after_the_lock(self, new_store: StoreFactory) -> None:
        limiter = LoginRateLimiter(max_failures=2, window_seconds=60, store=new_store())
        limiter.record_failure("d", now=0.0)
        limiter.record_failure("d", now=0.0)
        assert limiter.record_failure("d", now=61.0) is False
        assert limiter.is_locked("d", now=61.0) is False

    def test_keys_do_not_share_a_count(self, new_store: StoreFactory) -> None:
        limiter = LoginRateLimiter(max_failures=2, window_seconds=60, store=new_store())
        limiter.record_failure("e", now=0.0)
        assert limiter.record_failure("f", now=0.0) is False


class TestSharedAcrossReplicas:
    def test_failures_on_one_replica_lock_the_other(self, new_store: StoreFactory) -> None:
        """Covers: KAL-AUTH-034"""
        replica_a = LoginRateLimiter(max_failures=5, window_seconds=900, store=new_store())
        replica_b = LoginRateLimiter(max_failures=5, window_seconds=900, store=new_store())
        now = 1000.0
        for _ in range(5):
            replica_a.record_failure("203.0.113.9", now=now)
        assert replica_b.is_locked("203.0.113.9", now=now) is True
        assert replica_b.remaining_lock_seconds("203.0.113.9", now=now) == 900

    def test_failures_split_across_replicas_add_up(self, new_store: StoreFactory) -> None:
        """Covers: KAL-AUTH-034"""
        replica_a = LoginRateLimiter(max_failures=5, window_seconds=900, store=new_store())
        replica_b = LoginRateLimiter(max_failures=5, window_seconds=900, store=new_store())
        now = 1000.0
        for _ in range(2):
            assert replica_a.record_failure("203.0.113.9", now=now) is False
        for _ in range(2):
            assert replica_b.record_failure("203.0.113.9", now=now) is False
        assert replica_a.record_failure("203.0.113.9", now=now) is True
        assert replica_b.is_locked("203.0.113.9", now=now) is True

    def test_success_on_one_replica_clears_the_other(self, new_store: StoreFactory) -> None:
        replica_a = LoginRateLimiter(max_failures=2, window_seconds=900, store=new_store())
        replica_b = LoginRateLimiter(max_failures=2, window_seconds=900, store=new_store())
        replica_a.record_failure("g", now=0.0)
        replica_b.clear("g")
        assert replica_a.record_failure("g", now=0.0) is False


class TestRedisStore:
    def test_counts_live_under_the_kaleta_prefix_and_expire(
        self, redis_clients: RedisClientFactory, namespace: str
    ) -> None:
        client = redis_clients()
        store = RedisStore(namespace, client=client)
        assert store.add_failure("10.0.0.1", window_seconds=900, now=0.0) == 1
        assert store.add_failure("10.0.0.1", window_seconds=900, now=0.0) == 2
        key = f"kaleta:{namespace}:10.0.0.1"
        assert int(client.get(key) or 0) == 2
        assert 0 < int(client.ttl(key)) <= 900

    def test_a_count_left_without_expiry_gets_one(
        self, redis_clients: RedisClientFactory, namespace: str
    ) -> None:
        """A process that died between INCR and EXPIRE must not leave a count forever."""
        client = redis_clients()
        key = f"kaleta:{namespace}:10.0.0.2"
        client.set(key, 3)
        store = RedisStore(namespace, client=client)
        assert store.add_failure("10.0.0.2", window_seconds=900, now=0.0) == 4
        assert 0 < int(client.ttl(key)) <= 900

    def test_the_lock_key_expires_on_its_own(
        self, redis_clients: RedisClientFactory, namespace: str
    ) -> None:
        client = redis_clients()
        store = RedisStore(namespace, client=client)
        store.lock("10.0.0.1", until=1060.0, now=1000.0)
        assert store.locked_until("10.0.0.1") == 1060.0
        assert 0 < int(client.ttl(f"kaleta:{namespace}:10.0.0.1:lock")) <= 61

    def test_needs_a_url_or_a_client(self) -> None:
        with pytest.raises(ValueError, match="url or a client"):
            RedisStore("login")

    def test_connects_lazily_from_a_url(self) -> None:
        store = RedisStore("login", url="redis://127.0.0.1:1/0")
        assert store._client is None


class TestDefaultStore:
    def test_memory_without_a_redis_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(limit_mod.settings, "redis_url", None)
        assert isinstance(limit_mod.default_store("login"), MemoryStore)

    def test_redis_with_a_redis_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(limit_mod.settings, "redis_url", "redis://localhost:6379/0")
        store = limit_mod.default_store("login")
        assert isinstance(store, RedisStore)
        assert store._prefix == "kaleta:login:"
