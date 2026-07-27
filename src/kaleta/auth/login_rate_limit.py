# SPDX-License-Identifier: AGPL-3.0-or-later
"""In-memory login attempt counter (per client IP)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class _AttemptBucket:
    failures: int = 0
    locked_until: float = 0.0


@dataclass
class LoginRateLimiter:
    """Lock after ``max_failures`` failed logins for ``window_seconds``."""

    max_failures: int = 5
    window_seconds: float = 15 * 60
    _buckets: dict[str, _AttemptBucket] = field(default_factory=dict)

    def is_locked(self, key: str, *, now: float | None = None) -> bool:
        bucket = self._buckets.get(key)
        if bucket is None:
            return False
        current = now if now is not None else time.monotonic()
        return current < bucket.locked_until

    def remaining_lock_seconds(self, key: str, *, now: float | None = None) -> int:
        bucket = self._buckets.get(key)
        if bucket is None:
            return 0
        current = now if now is not None else time.monotonic()
        return max(0, int(bucket.locked_until - current))

    def record_failure(self, key: str, *, now: float | None = None) -> bool:
        """Record a failed attempt. Returns True if the key is now locked."""
        current = now if now is not None else time.monotonic()
        bucket = self._buckets.setdefault(key, _AttemptBucket())
        if current < bucket.locked_until:
            return True
        if bucket.locked_until and current >= bucket.locked_until:
            bucket.failures = 0
            bucket.locked_until = 0.0
        bucket.failures += 1
        if bucket.failures >= self.max_failures:
            bucket.locked_until = current + self.window_seconds
            bucket.failures = 0
            return True
        return False

    def clear(self, key: str) -> None:
        self._buckets.pop(key, None)


login_rate_limiter = LoginRateLimiter()
