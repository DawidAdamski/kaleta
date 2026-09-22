# SPDX-License-Identifier: AGPL-3.0-or-later
"""A session waiting on a second factor is not a session.

Covers: KAL-AUTH-016
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest

from kaleta.auth import middleware as middleware_mod
from kaleta.auth import session as session_mod
from kaleta.auth.session import MFA_CHALLENGE_TTL_MINUTES
from kaleta.services.mfa_service import STEP_UP_WINDOW_MINUTES, MfaService


@pytest.fixture
def fake_storage(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    store: dict[str, Any] = {}
    monkeypatch.setattr(session_mod, "app", MagicMock(storage=MagicMock(user=store)))
    return store


@pytest.fixture
def request_stub() -> Any:
    return MagicMock(url=MagicMock(path="/transactions"), method="GET")


class TestPendingSessionIsUnauthenticated:
    def test_the_challenge_does_not_authenticate(self, fake_storage: dict[str, Any]) -> None:
        """Covers: KAL-AUTH-016"""
        session_mod.begin_mfa_challenge(user_id=7, username="owner")
        assert session_mod.is_mfa_pending() is True
        assert session_mod.is_authenticated() is False
        assert fake_storage.get(session_mod.SESSION_AUTHENTICATED) is None

    def test_the_api_cookie_path_sees_nobody(
        self, fake_storage: dict[str, Any], request_stub: Any
    ) -> None:
        """Covers: KAL-AUTH-016

        ``user_id_from_request`` is what lets a browser session read
        ``/api/v1``. A pending challenge must not open that door either.
        """
        session_mod.begin_mfa_challenge(user_id=7, username="owner")
        assert session_mod.user_id_from_request(request_stub) is None

    def test_finishing_the_challenge_authenticates(self, fake_storage: dict[str, Any]) -> None:
        session_mod.begin_mfa_challenge(user_id=7, username="owner")
        session_mod.login_session(user_id=7, username="owner")
        assert session_mod.is_mfa_pending() is False
        assert session_mod.is_authenticated() is True

    def test_the_pending_user_is_remembered(self, fake_storage: dict[str, Any]) -> None:
        session_mod.begin_mfa_challenge(user_id=7, username="owner")
        assert session_mod.mfa_pending_user() == (7, "owner")

    def test_no_challenge_means_no_pending_user(self, fake_storage: dict[str, Any]) -> None:
        assert session_mod.mfa_pending_user() is None

    def test_logout_clears_the_challenge(self, fake_storage: dict[str, Any]) -> None:
        session_mod.begin_mfa_challenge(user_id=7, username="owner")
        session_mod.logout_session()
        assert session_mod.is_mfa_pending() is False
        assert session_mod.mfa_pending_user() is None

    def test_a_stale_challenge_is_no_challenge(self, fake_storage: dict[str, Any]) -> None:
        """A browser left at the code prompt must not stay one code from a login."""
        session_mod.begin_mfa_challenge(user_id=7, username="owner")
        stale = datetime.now(UTC) - timedelta(minutes=MFA_CHALLENGE_TTL_MINUTES + 1)
        fake_storage[session_mod.SESSION_MFA_PENDING_AT] = stale.isoformat()
        assert session_mod.mfa_pending_user() is None
        assert session_mod.is_mfa_pending() is False

    def test_a_challenge_without_a_stamp_is_no_challenge(
        self, fake_storage: dict[str, Any]
    ) -> None:
        fake_storage[session_mod.SESSION_MFA_PENDING] = True
        fake_storage[session_mod.SESSION_MFA_PENDING_USER_ID] = 7
        fake_storage[session_mod.SESSION_MFA_PENDING_USERNAME] = "owner"
        assert session_mod.mfa_pending_user() is None

    def test_signing_in_clears_a_leftover_challenge(self, fake_storage: dict[str, Any]) -> None:
        session_mod.begin_mfa_challenge(user_id=7, username="owner")
        session_mod.login_session(user_id=7, username="owner")
        assert session_mod.is_mfa_pending() is False


class TestRoutesReachableWhilePending:
    def test_the_code_page_is_public(self) -> None:
        """Covers: KAL-AUTH-016

        It has to be: the guard cannot let a half-authenticated session
        through, so the page guards itself instead.
        """
        assert middleware_mod.is_public_path("/login/mfa") is True

    @pytest.mark.parametrize("path", ["/transactions", "/", "/settings", "/accounts"])
    def test_data_pages_are_not_public(self, path: str) -> None:
        """Covers: KAL-AUTH-016"""
        assert middleware_mod.is_public_path(path) is False


class TestStepUpStamp:
    """The session reports *when*; ``MfaService`` decides whether that is fresh."""

    def test_nothing_verified_is_no_stamp(self, fake_storage: dict[str, Any]) -> None:
        assert session_mod.mfa_verified_at() is None
        assert MfaService.step_up_is_fresh(session_mod.mfa_verified_at()) is False

    def test_a_fresh_code_counts(self, fake_storage: dict[str, Any]) -> None:
        session_mod.mark_mfa_verified()
        assert MfaService.step_up_is_fresh(session_mod.mfa_verified_at()) is True

    def test_an_old_code_does_not(self, fake_storage: dict[str, Any]) -> None:
        stale = datetime.now(UTC) - timedelta(minutes=STEP_UP_WINDOW_MINUTES + 1)
        fake_storage[session_mod.SESSION_MFA_VERIFIED_AT] = stale.isoformat()
        assert MfaService.step_up_is_fresh(session_mod.mfa_verified_at()) is False

    def test_a_broken_stamp_reads_as_none(self, fake_storage: dict[str, Any]) -> None:
        fake_storage[session_mod.SESSION_MFA_VERIFIED_AT] = "not a timestamp"
        assert session_mod.mfa_verified_at() is None

    def test_logout_forgets_the_step_up(self, fake_storage: dict[str, Any]) -> None:
        session_mod.mark_mfa_verified()
        session_mod.logout_session()
        assert session_mod.mfa_verified_at() is None
