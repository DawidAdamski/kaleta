# SPDX-License-Identifier: AGPL-3.0-or-later
"""Resend-confirmation throttle and the local-login answer to e-mail links."""

from __future__ import annotations

from collections.abc import Generator

import pytest

from kaleta.auth import sign_in as sign_in_mod
from kaleta.auth.login_rate_limit import MemoryStore, SendThrottle
from kaleta.auth.providers import RegistryAuthProvider, set_auth_provider
from kaleta.exceptions import ValidationError


class TestSendThrottle:
    def test_first_send_is_allowed(self) -> None:
        assert SendThrottle(store=MemoryStore()).allow("ania@example.com", now=1000.0) is True

    def test_a_second_send_within_the_interval_is_refused(self) -> None:
        throttle = SendThrottle(store=MemoryStore())
        throttle.allow("ania@example.com", now=1000.0)
        assert throttle.allow("ania@example.com", now=1059.0) is False

    def test_sending_is_allowed_again_after_the_interval(self) -> None:
        throttle = SendThrottle(store=MemoryStore())
        throttle.allow("ania@example.com", now=1000.0)
        assert throttle.allow("ania@example.com", now=1060.0) is True

    def test_addresses_are_throttled_separately(self) -> None:
        throttle = SendThrottle(store=MemoryStore())
        throttle.allow("ania@example.com", now=1000.0)
        assert throttle.allow("jan@example.com", now=1001.0) is True


class _CountingProvider(RegistryAuthProvider):
    name = "supabase"

    def __init__(self) -> None:
        self.resent: list[str] = []

    async def resend_confirmation(self, email: str) -> None:
        self.resent.append(email)


@pytest.fixture
def counting() -> Generator[_CountingProvider]:
    provider = _CountingProvider()
    set_auth_provider(provider)
    original = sign_in_mod.resend_throttle
    sign_in_mod.resend_throttle = SendThrottle(store=MemoryStore())
    try:
        yield provider
    finally:
        sign_in_mod.resend_throttle = original
        set_auth_provider(None)


async def test_resend_reaches_the_provider_once_per_interval(counting: _CountingProvider) -> None:
    """Covers: KAL-TEN-006"""
    await sign_in_mod.resend_confirmation("ania@example.com")
    await sign_in_mod.resend_confirmation(" ANIA@example.com ")
    assert counting.resent == ["ania@example.com"]


@pytest.mark.parametrize(
    "call",
    ["resend_confirmation", "request_magic_link", "verify_magic_link"],
)
async def test_local_logins_send_no_mail(call: str) -> None:
    with pytest.raises(ValidationError, match="sends no e-mail"):
        await getattr(RegistryAuthProvider(), call)("ania@example.com")
