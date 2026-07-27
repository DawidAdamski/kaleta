# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for LoginRateLimiter."""

from __future__ import annotations

from kaleta.auth.login_rate_limit import LoginRateLimiter


class TestLoginRateLimiter:
    def test_locks_after_max_failures(self) -> None:
        """Covers: KAL-AUTH-008"""
        limiter = LoginRateLimiter(max_failures=5, window_seconds=900)
        now = 1000.0
        for _ in range(4):
            assert limiter.record_failure("127.0.0.1", now=now) is False
            assert limiter.is_locked("127.0.0.1", now=now) is False
        assert limiter.record_failure("127.0.0.1", now=now) is True
        assert limiter.is_locked("127.0.0.1", now=now) is True
        assert limiter.remaining_lock_seconds("127.0.0.1", now=now) == 900

    def test_clear_unlocks(self) -> None:
        limiter = LoginRateLimiter(max_failures=2, window_seconds=60)
        now = 50.0
        limiter.record_failure("a", now=now)
        limiter.record_failure("a", now=now)
        assert limiter.is_locked("a", now=now)
        limiter.clear("a")
        assert limiter.is_locked("a", now=now) is False

    def test_lock_expires(self) -> None:
        limiter = LoginRateLimiter(max_failures=1, window_seconds=10)
        limiter.record_failure("b", now=0.0)
        assert limiter.is_locked("b", now=5.0)
        assert limiter.is_locked("b", now=10.0) is False
