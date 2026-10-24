# SPDX-License-Identifier: AGPL-3.0-or-later
"""Per-instance throttle on the manual "Fetch NBP rates" button.

One fetch serves the whole instance (``public.nbp_rates``) and NBP publishes
Table A once a business day, so a refresh more than once every 15 minutes can
add nothing. The button marks the throttle only after a successful fetch and
reads ``retry_after_seconds`` before the next one; a failed fetch stays
retryable. The store is built the way the app builds it at import —
``default_store`` with ``KALETA_REDIS_URL`` set — so the Redis path runs on the
CI ``valkey`` job and an in-process fakeredis server otherwise.

Covers: KAL-FXR-005
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
from kaleta.auth.login_rate_limit import SendThrottle

#: Literals from KAL-FXR-005: a 15-minute minimum interval.
INTERVAL_SECONDS = 15 * 60


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


def _throttle(namespace: str) -> SendThrottle:
    return SendThrottle(
        interval_seconds=INTERVAL_SECONDS,
        store=limit_mod.default_store(namespace),
    )


def test_a_success_blocks_the_next_fetch_for_fifteen_minutes(namespace: str) -> None:
    """Covers: KAL-FXR-005

    After a successful fetch the button marks the throttle; a second press
    within 15 minutes is refused, with the full window remaining, so no HTTP
    request to NBP is made.
    """
    throttle = _throttle(namespace)
    key = "table_a"
    now = 1000.0

    # A fetch has just succeeded.
    throttle.mark(key, now=now)

    # A press one second later is throttled, with ~15 minutes still to wait.
    remaining = throttle.retry_after_seconds(key, now=now + 1)
    assert remaining > 0
    assert remaining == INTERVAL_SECONDS - 1


def test_the_interval_frees_up_after_fifteen_minutes(namespace: str) -> None:
    """Covers: KAL-FXR-005

    Once 15 minutes have passed the throttle is clear, so the button fetches
    from NBP again.
    """
    throttle = _throttle(namespace)
    key = "table_a"
    now = 1000.0

    throttle.mark(key, now=now)
    assert throttle.retry_after_seconds(key, now=now + INTERVAL_SECONDS) == 0


def test_reading_the_throttle_does_not_start_it(namespace: str) -> None:
    """Covers: KAL-FXR-005

    A failed fetch never calls ``mark``; the read alone must not lock the
    button, or a transient network blip would block a legitimate retry.
    """
    throttle = _throttle(namespace)
    key = "table_a"
    now = 1000.0

    # Simulate "button pressed, read the throttle, fetch failed, no mark".
    assert throttle.retry_after_seconds(key, now=now) == 0
    assert throttle.retry_after_seconds(key, now=now + 1) == 0

    # The very next press (a retry) is still allowed.
    assert throttle.retry_after_seconds(key, now=now + 2) == 0
