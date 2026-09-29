# SPDX-License-Identifier: AGPL-3.0-or-later
"""Failed-attempt counters for login and the second factor.

The counting lives in ``LoginRateLimiter``; where the counts are kept is an
``AttemptStore``. ``MemoryStore`` is a dict in the process — right for one
process on a laptop. ``RedisStore`` keeps them in Redis, so that every
replica sees the same count and a restart does not hand out a fresh five.
``KALETA_REDIS_URL`` picks the store, the same variable that moves NiceGUI's
session storage (see ``main.py``): an operator sets one thing and both move.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from kaleta.config import settings

if TYPE_CHECKING:
    from redis import Redis

logger = logging.getLogger(__name__)

#: Prefix of every limiter key in Redis. NiceGUI's own keys sit under
#: ``kaleta:`` too (``NICEGUI_REDIS_KEY_PREFIX``) but are ``kaleta:user-…``,
#: ``kaleta:tab-…`` and ``kaleta:general``, so the two never meet.
REDIS_KEY_PREFIX = "kaleta:"


class AttemptStore(Protocol):
    """Where a limiter keeps its failure counts and locks.

    Times are wall-clock seconds (``time.time()``): a monotonic clock is
    per-process, and a lock written by one replica is read by another.
    """

    def add_failure(self, key: str, *, window_seconds: float, now: float) -> int:
        """Count one failure and return the count.

        A count expires ``window_seconds`` after its first failure, so a
        mistyped password on Monday does not help lock the account on Friday.
        """
        ...

    def reset_failures(self, key: str) -> None: ...

    def lock(self, key: str, *, until: float, now: float) -> None:
        """Lock ``key`` until the wall-clock time ``until``."""
        ...

    def locked_until(self, key: str) -> float:
        """When the lock on ``key`` ends; ``0.0`` when there is none."""
        ...

    def clear(self, key: str) -> None:
        """Forget the count and the lock."""
        ...


@dataclass
class _Counter:
    failures: int = 0
    expires_at: float = 0.0


@dataclass
class MemoryStore:
    """Counts in a dict: one process, gone on restart."""

    _counters: dict[str, _Counter] = field(default_factory=dict)
    _locks: dict[str, float] = field(default_factory=dict)

    def add_failure(self, key: str, *, window_seconds: float, now: float) -> int:
        counter = self._counters.get(key)
        if counter is None or now >= counter.expires_at:
            counter = _Counter(expires_at=now + window_seconds)
            self._counters[key] = counter
        counter.failures += 1
        return counter.failures

    def reset_failures(self, key: str) -> None:
        self._counters.pop(key, None)

    def lock(self, key: str, *, until: float, now: float) -> None:
        self._locks[key] = until

    def locked_until(self, key: str) -> float:
        return self._locks.get(key, 0.0)

    def clear(self, key: str) -> None:
        self._counters.pop(key, None)
        self._locks.pop(key, None)


class RedisStore:
    """Counts in Redis: ``INCR`` + ``EXPIRE`` on ``kaleta:<namespace>:<key>``.

    The lock is a second key holding its end time, with an ``EXPIRE`` so Redis
    drops it by itself. The value, not the TTL, says whether it still holds,
    which keeps the store honest about the ``now`` it is given.

    ``redis`` is imported on first use: it is the ``hosted`` extra, and a
    local install without it never builds one of these.
    """

    def __init__(
        self,
        namespace: str,
        *,
        url: str | None = None,
        client: Redis | None = None,
    ) -> None:
        if url is None and client is None:
            msg = "RedisStore needs a url or a client"
            raise ValueError(msg)
        self._prefix = f"{REDIS_KEY_PREFIX}{namespace}:"
        self._url = url
        self._client = client

    def _redis(self) -> Redis:
        if self._client is None:
            from redis import Redis

            if self._url is None:
                msg = "RedisStore needs a url or a client"
                raise ValueError(msg)
            # Short timeouts: these calls sit on the login path, and a Redis
            # that does not answer must fail the attempt, not hang it.
            self._client = Redis.from_url(self._url, socket_connect_timeout=2, socket_timeout=2)
        return self._client

    def _count_key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    def _lock_key(self, key: str) -> str:
        return f"{self._prefix}{key}:lock"

    def add_failure(self, key: str, *, window_seconds: float, now: float) -> int:
        redis = self._redis()
        name = self._count_key(key)
        pipe = redis.pipeline()
        pipe.incr(name)
        pipe.ttl(name)
        count, ttl = pipe.execute()
        # -1: the key has no expiry — it was just created, or a process died
        # between the INCR and the EXPIRE of an earlier call. Either way it
        # gets one now, so no count outlives its window for good.
        if ttl == -1:
            redis.expire(name, max(1, int(window_seconds)))
        return int(count)

    def reset_failures(self, key: str) -> None:
        self._redis().delete(self._count_key(key))

    def lock(self, key: str, *, until: float, now: float) -> None:
        ttl = max(1, int(until - now) + 1)
        self._redis().set(self._lock_key(key), repr(until), ex=ttl)

    def locked_until(self, key: str) -> float:
        raw = self._redis().get(self._lock_key(key))
        if raw is None:
            return 0.0
        return float(raw.decode() if isinstance(raw, bytes) else raw)

    def clear(self, key: str) -> None:
        self._redis().delete(self._count_key(key), self._lock_key(key))


def default_store(namespace: str) -> AttemptStore:
    """``RedisStore`` when ``KALETA_REDIS_URL`` is set, else ``MemoryStore``."""
    if settings.redis_url:
        logger.debug("Rate limiter %r keeps its counts in Redis", namespace)
        return RedisStore(namespace, url=settings.redis_url)
    return MemoryStore()


@dataclass
class LoginRateLimiter:
    """Lock after ``max_failures`` failed attempts for ``window_seconds``.

    Not atomic across replicas: two failures landing at the same moment on
    two replicas can both cross the threshold and both write the lock. The
    outcome is still one lock, ending a moment later at most.
    """

    max_failures: int = 5
    window_seconds: float = 15 * 60
    store: AttemptStore = field(default_factory=MemoryStore)

    def is_locked(self, key: str, *, now: float | None = None) -> bool:
        current = now if now is not None else time.time()
        return current < self.store.locked_until(key)

    def remaining_lock_seconds(self, key: str, *, now: float | None = None) -> int:
        current = now if now is not None else time.time()
        return max(0, int(self.store.locked_until(key) - current))

    def record_failure(self, key: str, *, now: float | None = None) -> bool:
        """Record a failed attempt. Returns True if the key is now locked."""
        current = now if now is not None else time.time()
        if self.is_locked(key, now=current):
            return True
        failures = self.store.add_failure(key, window_seconds=self.window_seconds, now=current)
        if failures >= self.max_failures:
            self.store.lock(key, until=current + self.window_seconds, now=current)
            self.store.reset_failures(key)
            return True
        return False

    def clear(self, key: str) -> None:
        self.store.clear(key)


#: Failed passwords, keyed by client IP.
login_rate_limiter = LoginRateLimiter(store=default_store("login"))

#: Failed second factors, keyed by user id. Separate from the password
#: limiter: the password is already right at this point, so burning the IP
#: bucket would lock the account out of a retry it is entitled to, and sharing
#: a bucket would let a wrong code hide a password-guessing run.
mfa_rate_limiter = LoginRateLimiter(store=default_store("mfa"))
