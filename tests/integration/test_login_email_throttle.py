# SPDX-License-Identifier: AGPL-3.0-or-later
"""Per-e-mail login throttle: wrong passwords for one e-mail lock it regardless
of source address, which the IP-keyed limiter alone cannot do.

Each limiter builds its store the way the app does at import — ``default_store``
with ``KALETA_REDIS_URL`` set — so the Redis path runs on the CI ``valkey`` job
and an in-process fakeredis server otherwise, the way two separate namespaces
behind one backend behave.

Covers: KAL-AUTH-042
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
from kaleta.auth.login_rate_limit import LoginRateLimiter

#: Literals from KAL-AUTH-042: five wrong passwords, a 15-minute lock.
MAX_FAILURES = 5
LOCK_SECONDS = 15 * 60


@pytest.fixture
def namespace(monkeypatch: pytest.MonkeyPatch) -> Generator[str]:
    """Point settings at Redis (or fakeredis); give this test a prefix of its own."""
    url = os.environ.get("KALETA_REDIS_URL")
    if url is None:
        server = fakeredis.FakeServer()

        def _from_url(_url: str, **_kwargs: Any) -> Redis:
            return fakeredis.FakeRedis(server=server)

        monkeypatch.setattr(Redis, "from_url", staticmethod(_from_url))
    monkeypatch.setattr(limit_mod.settings, "redis_url", url or "redis://fake-shared-redis:6379/0")
    ns = f"it-{uuid.uuid4().hex}"
    yield ns
    if url is not None:
        client = Redis.from_url(url)
        keys = list(client.scan_iter(match=f"kaleta:{ns}:*"))
        if keys:
            client.delete(*keys)
        client.close()


def _limiter(namespace: str) -> LoginRateLimiter:
    return LoginRateLimiter(
        max_failures=MAX_FAILURES,
        window_seconds=LOCK_SECONDS,
        store=limit_mod.default_store(namespace),
    )


def test_one_email_from_many_addresses_locks_the_email(namespace: str) -> None:
    """Covers: KAL-AUTH-042

    Five wrong passwords for one e-mail, each from a different client address,
    as ``login.py::_submit`` records them: a failure on the IP limiter (keyed by
    the address) and on the e-mail limiter (keyed by the normalised e-mail). No
    single address reaches five failures, so the IP limiter alone locks nothing;
    the e-mail limiter, counting all five under one key, locks the e-mail.
    """
    ip_limiter = _limiter(f"{namespace}-login")
    email_limiter = _limiter(f"{namespace}-login_email")
    email_key = "victim@example.test"
    addresses = ["203.0.113.1", "203.0.113.2", "203.0.113.3", "203.0.113.4", "203.0.113.5"]
    now = 1000.0

    email_locked = False
    for address in addresses:
        assert ip_limiter.record_failure(address, now=now) is False
        email_locked = email_limiter.record_failure(email_key, now=now)

    # No single client address crossed the threshold, so the IP limiter is clear.
    for address in addresses:
        assert ip_limiter.is_locked(address, now=now) is False

    # The five failures for one e-mail did lock it, for the 15-minute window.
    assert email_locked is True
    assert email_limiter.is_locked(email_key, now=now) is True
    assert email_limiter.remaining_lock_seconds(email_key, now=now) == LOCK_SECONDS


def test_the_email_key_is_case_insensitive(namespace: str) -> None:
    """Covers: KAL-AUTH-042

    The view lower-cases the e-mail before keying, so the same address in mixed
    case shares one bucket and cannot sidestep the lock.
    """
    email_limiter = _limiter(f"{namespace}-login_email")
    now = 1000.0
    for _ in range(MAX_FAILURES):
        email_limiter.record_failure("victim@example.test", now=now)
    assert email_limiter.is_locked("victim@example.test", now=now) is True
