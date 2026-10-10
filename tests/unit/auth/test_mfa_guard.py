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
from kaleta.schemas.identity import Identity, MfaRequired
from kaleta.services.mfa_service import STEP_UP_WINDOW_MINUTES, MfaService


@pytest.fixture
def fake_storage(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    store: dict[str, Any] = {}
    monkeypatch.setattr(session_mod, "app", MagicMock(storage=MagicMock(user=store)))
    return store


@pytest.fixture
def request_stub() -> Any:
    return MagicMock(url=MagicMock(path="/transactions"), method="GET")


_PENDING = MfaRequired(
    identity=Identity(subject="local:7", email="owner@example.com", email_verified=True),
    factor_id="local",
)


@pytest.fixture(autouse=True)
def _no_parked_challenges() -> Any:
    session_mod.hosted_mfa_challenges._items.clear()
    yield
    session_mod.hosted_mfa_challenges._items.clear()


class TestPendingSessionIsUnauthenticated:
    def test_the_challenge_does_not_authenticate(self, fake_storage: dict[str, Any]) -> None:
        """Covers: KAL-AUTH-016"""
        session_mod.begin_hosted_mfa_challenge(_PENDING)
        assert session_mod.is_hosted_mfa_pending() is True
        assert session_mod.is_authenticated() is False
        assert fake_storage.get(session_mod.SESSION_AUTHENTICATED) is None

    def test_the_api_cookie_path_sees_nobody(
        self, fake_storage: dict[str, Any], request_stub: Any
    ) -> None:
        """Covers: KAL-AUTH-016

        ``user_id_from_request`` is what lets a browser session read
        ``/api/v1``. A pending challenge must not open that door either.
        """
        session_mod.begin_hosted_mfa_challenge(_PENDING)
        assert session_mod.user_id_from_request(request_stub) is None

    def test_the_pending_sign_in_is_remembered(self, fake_storage: dict[str, Any]) -> None:
        session_mod.begin_hosted_mfa_challenge(_PENDING)
        assert session_mod.hosted_mfa_pending() == _PENDING

    def test_no_challenge_means_no_pending_sign_in(self, fake_storage: dict[str, Any]) -> None:
        assert session_mod.hosted_mfa_pending() is None

    def test_logout_clears_the_challenge(self, fake_storage: dict[str, Any]) -> None:
        session_mod.begin_hosted_mfa_challenge(_PENDING)
        session_mod.logout_session()
        assert session_mod.is_hosted_mfa_pending() is False
        assert session_mod.hosted_mfa_pending() is None

    def test_an_expiry_is_distinguishable_from_never_having_had_one(
        self, fake_storage: dict[str, Any]
    ) -> None:
        """`/login/mfa` needs the difference: one case has an expiry to
        explain and a deep link to keep, the other has neither."""
        assert session_mod.is_hosted_mfa_pending() is False

        session_mod.begin_hosted_mfa_challenge(_PENDING)
        stale = datetime.now(UTC) - timedelta(minutes=11)
        fake_storage[session_mod.SESSION_HOSTED_MFA_AT] = stale.isoformat()

        # True before the read that clears it, which is the order the page uses.
        assert session_mod.is_hosted_mfa_pending() is True
        assert session_mod.hosted_mfa_pending() is None
        assert session_mod.is_hosted_mfa_pending() is False

    def test_a_stale_challenge_is_no_challenge(self, fake_storage: dict[str, Any]) -> None:
        """A browser left at the code prompt must not stay one code from a login."""
        session_mod.begin_hosted_mfa_challenge(_PENDING)
        # The scenario's literal ten, pinned rather than read off the constant:
        # widening the window to an hour must fail here, not pass quietly.
        assert MFA_CHALLENGE_TTL_MINUTES == 10, "KAL-AUTH-021 says ten minutes"
        stale = datetime.now(UTC) - timedelta(minutes=11)
        fake_storage[session_mod.SESSION_HOSTED_MFA_AT] = stale.isoformat()
        assert session_mod.hosted_mfa_pending() is None
        assert session_mod.is_hosted_mfa_pending() is False

    def test_a_challenge_without_a_stamp_is_no_challenge(
        self, fake_storage: dict[str, Any]
    ) -> None:
        session_mod.begin_hosted_mfa_challenge(_PENDING)
        del fake_storage[session_mod.SESSION_HOSTED_MFA_AT]
        assert session_mod.hosted_mfa_pending() is None
        assert session_mod.is_hosted_mfa_pending() is False

    def test_a_challenge_this_process_never_parked_clears_itself(
        self, fake_storage: dict[str, Any]
    ) -> None:
        """After a restart the reference points at nothing: back to the password."""
        session_mod.begin_hosted_mfa_challenge(_PENDING)
        session_mod.hosted_mfa_challenges._items.clear()
        assert session_mod.hosted_mfa_pending() is None
        assert session_mod.is_hosted_mfa_pending() is False

    def test_signing_in_clears_a_leftover_challenge(self, fake_storage: dict[str, Any]) -> None:
        session_mod.begin_hosted_mfa_challenge(_PENDING)
        session_mod.login_session(user_id=7, username="owner")
        assert session_mod.is_hosted_mfa_pending() is False
        assert session_mod.is_authenticated() is True


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
        assert STEP_UP_WINDOW_MINUTES == 10, "KAL-AUTH-017 says ten minutes"
        stale = datetime.now(UTC) - timedelta(minutes=11)
        fake_storage[session_mod.SESSION_MFA_VERIFIED_AT] = stale.isoformat()
        assert MfaService.step_up_is_fresh(session_mod.mfa_verified_at()) is False

    def test_a_broken_stamp_reads_as_none(self, fake_storage: dict[str, Any]) -> None:
        fake_storage[session_mod.SESSION_MFA_VERIFIED_AT] = "not a timestamp"
        assert session_mod.mfa_verified_at() is None

    def test_logout_forgets_the_step_up(self, fake_storage: dict[str, Any]) -> None:
        session_mod.mark_mfa_verified()
        session_mod.logout_session()
        assert session_mod.mfa_verified_at() is None
