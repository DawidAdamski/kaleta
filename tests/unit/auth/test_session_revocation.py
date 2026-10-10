# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for server-side session revocation (the ``sessions_valid_from`` watermark).

The guards themselves — middleware and API cookie path against a real
database — are in ``tests/integration/test_session_revocation_guards.py``.

Covers: KAL-AUTH-035
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.auth import revocation_cache as cache_mod
from kaleta.auth import session as session_mod
from kaleta.auth.revocation_cache import RevocationCache, revocation_cache
from kaleta.models.user import User
from kaleta.services.auth_service import AuthService


def _ago(**kwargs: float) -> str:
    return (datetime.now(UTC) - timedelta(**kwargs)).isoformat()


@pytest.fixture(autouse=True)
def _empty_cache() -> Iterator[None]:
    revocation_cache.clear()
    yield
    revocation_cache.clear()


@pytest.fixture
def fake_storage(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    store: dict[str, Any] = {}
    monkeypatch.setattr(session_mod.app, "storage", MagicMock(user=store))
    return store


@pytest.fixture
def cache_reads_test_db(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Point the watermark cache at the test database; return a log of its reads."""
    reads: list[int] = []

    async def _with_session(fn: Callable[[AsyncSession], Awaitable[Any]]) -> Any:
        reads.append(1)
        return await fn(session)

    monkeypatch.setattr(cache_mod, "with_session", _with_session)
    return reads


@pytest.fixture
def user(suite_owner: User) -> User:
    return suite_owner


class TestWatermark:
    async def test_new_user_was_never_revoked(self, session: AsyncSession, user: User) -> None:
        assert await AuthService(session).sessions_valid_from(user.id) is None

    async def test_revoke_sets_a_utc_watermark(self, session: AsyncSession, user: User) -> None:
        before = datetime.now(UTC)
        stamp = await AuthService(session).revoke_sessions(user.id)
        stored = await AuthService(session).sessions_valid_from(user.id)
        assert stored == stamp
        assert stored is not None
        assert stored.tzinfo is not None
        assert stored >= before


class TestRevocationCache:
    async def test_second_read_inside_ttl_is_served_from_memory(
        self, session: AsyncSession, user: User, cache_reads_test_db: list[int]
    ) -> None:
        cache = RevocationCache()
        assert await cache.valid_from(user.id) is None
        await AuthService(session).revoke_sessions(user.id)
        # Still the remembered answer: a bump from another process is only
        # promised to be seen within the TTL.
        assert await cache.valid_from(user.id) is None
        assert len(cache_reads_test_db) == 1

    async def test_read_after_ttl_goes_back_to_the_database(
        self, session: AsyncSession, user: User, cache_reads_test_db: list[int]
    ) -> None:
        cache = RevocationCache(ttl_seconds=0)
        assert await cache.valid_from(user.id) is None
        stamp = await AuthService(session).revoke_sessions(user.id)
        assert await cache.valid_from(user.id) == stamp
        assert len(cache_reads_test_db) == 2

    async def test_forget_makes_a_bump_visible_at_once(
        self, session: AsyncSession, user: User, cache_reads_test_db: list[int]
    ) -> None:
        cache = RevocationCache()
        assert await cache.valid_from(user.id) is None
        stamp = await AuthService(session).revoke_sessions(user.id)
        cache.forget(user.id)
        assert await cache.valid_from(user.id) == stamp

    def test_default_ttl_is_one_minute(self) -> None:
        assert cache_mod.TTL_SECONDS == 60.0


class TestSessionRevoked:
    async def test_never_revoked_user_keeps_any_session(
        self, user: User, cache_reads_test_db: list[int]
    ) -> None:
        assert await session_mod.session_revoked(user.id, None) is False

    async def test_session_signed_in_before_the_bump_is_revoked(
        self, session: AsyncSession, user: User, cache_reads_test_db: list[int]
    ) -> None:
        login_at = datetime.now(UTC) - timedelta(minutes=5)
        await AuthService(session).revoke_sessions(user.id)
        assert await session_mod.session_revoked(user.id, login_at) is True

    async def test_session_signed_in_after_the_bump_is_kept(
        self, session: AsyncSession, user: User, cache_reads_test_db: list[int]
    ) -> None:
        await AuthService(session).revoke_sessions(user.id)
        assert await session_mod.session_revoked(user.id, datetime.now(UTC)) is False

    async def test_session_without_a_stamp_is_revoked_once_there_is_a_watermark(
        self, session: AsyncSession, user: User, cache_reads_test_db: list[int]
    ) -> None:
        await AuthService(session).revoke_sessions(user.id)
        assert await session_mod.session_revoked(user.id, None) is True


class TestIssuedAt:
    def test_no_stamps(self, fake_storage: dict[str, Any]) -> None:
        assert session_mod.session_issued_at() is None

    def test_later_of_login_and_revalidation(self, fake_storage: dict[str, Any]) -> None:
        fake_storage[session_mod.SESSION_LOGIN_AT] = _ago(hours=2)
        revalidated = _ago(minutes=1)
        fake_storage[session_mod.SESSION_REVALIDATED_AT] = revalidated
        assert session_mod.session_issued_at() == datetime.fromisoformat(revalidated)

    async def test_the_session_that_made_the_change_stays_in(
        self,
        session: AsyncSession,
        user: User,
        fake_storage: dict[str, Any],
        cache_reads_test_db: list[int],
    ) -> None:
        """Covers: KAL-AUTH-035"""
        fake_storage[session_mod.SESSION_USER_ID] = user.id
        fake_storage[session_mod.SESSION_LOGIN_AT] = _ago(hours=2)
        # Cached before the change, so only `forget` can make it visible.
        assert await session_mod.current_session_revoked() is False
        await AuthService(session).revoke_sessions(user.id)
        session_mod.keep_session_after_revocation(user.id)
        assert await session_mod.current_session_revoked() is False
        # The login stamp — and with it the absolute TTL — did not move.
        assert (
            fake_storage[session_mod.SESSION_LOGIN_AT]
            != fake_storage[session_mod.SESSION_REVALIDATED_AT]
        )
        # A second browser that signed in at the same time is out.
        assert (
            await session_mod.session_revoked(
                user.id, datetime.fromisoformat(fake_storage[session_mod.SESSION_LOGIN_AT])
            )
            is True
        )

    def test_logout_drops_the_revalidation_stamp(self, fake_storage: dict[str, Any]) -> None:
        fake_storage[session_mod.SESSION_REVALIDATED_AT] = _ago(minutes=1)
        session_mod.logout_session()
        assert session_mod.SESSION_REVALIDATED_AT not in fake_storage
