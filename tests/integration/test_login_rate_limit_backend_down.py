# SPDX-License-Identifier: AGPL-3.0-or-later
"""The limiter fails closed on an unreachable backend, and in a way views catch.

With ``KALETA_REDIS_URL`` set and Redis unreachable, every ``RedisStore`` call
raises. The login / MFA / Security views wrap each limiter call in
``except RATE_LIMITER_BACKEND_ERRORS`` so the failure becomes a "try again
shortly" toast instead of a dead click. This pins the contract those views
rely on: the exception the limiter actually raises when the backend is down is
one the tuple catches, and the tuple is not empty when ``redis`` is installed.

The visible toast itself is walked by hand (KAL-AUTH-041 @manual): its only
faithful trigger — Redis unreachable — also backs NiceGUI's session storage,
so the login page 500s before the submit handler runs, which the e2e harness
cannot reproduce.

Covers: KAL-AUTH-041
"""

from __future__ import annotations

from typing import Any

import pytest

pytest.importorskip("redis")

from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError

from kaleta.auth.login_rate_limit import (
    RATE_LIMITER_BACKEND_ERRORS,
    LoginRateLimiter,
    RedisStore,
)


class _UnreachableRedis:
    """A redis client whose server cannot be reached: every command raises."""

    def _boom(self, *_args: Any, **_kwargs: Any) -> Any:
        raise RedisConnectionError("Error connecting to Redis (test stub)")

    # The commands RedisStore uses across all its methods.
    pipeline = _boom
    get = _boom
    set = _boom
    delete = _boom
    incr = _boom
    ttl = _boom
    expire = _boom


def _limiter() -> LoginRateLimiter:
    store = RedisStore("login", client=_UnreachableRedis())
    return LoginRateLimiter(store=store)


def test_backend_errors_tuple_is_populated_when_redis_is_installed() -> None:
    """Covers: KAL-AUTH-041

    The views' ``except RATE_LIMITER_BACKEND_ERRORS`` must actually catch
    something where Redis is in use; an empty tuple would silently re-open the
    dead-click bug.
    """
    assert (RedisError,) == RATE_LIMITER_BACKEND_ERRORS


@pytest.mark.parametrize(
    "call",
    [
        pytest.param(lambda lim: lim.is_locked("198.51.100.7"), id="is_locked"),
        pytest.param(lambda lim: lim.remaining_lock_seconds("198.51.100.7"), id="remaining"),
        pytest.param(lambda lim: lim.record_failure("198.51.100.7"), id="record_failure"),
        pytest.param(lambda lim: lim.clear("198.51.100.7"), id="clear"),
    ],
)
def test_limiter_backend_failure_is_caught_by_the_views_tuple(call: Any) -> None:
    """Covers: KAL-AUTH-041

    Each limiter call the views make raises when the backend is down, and the
    raised exception is one ``RATE_LIMITER_BACKEND_ERRORS`` catches — so the
    ``except`` clauses in the views genuinely fire.
    """
    limiter = _limiter()
    with pytest.raises(RATE_LIMITER_BACKEND_ERRORS):
        call(limiter)
