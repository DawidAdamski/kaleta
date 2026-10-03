# SPDX-License-Identifier: AGPL-3.0-or-later
"""``AuthProvider`` implementations, chosen by ``KALETA_AUTH_BACKEND``."""

from __future__ import annotations

from kaleta.auth.providers.base import (
    AuthProvider,
    FactorEnrolment,
    Identity,
    MfaRequired,
    SignUpResult,
)
from kaleta.auth.providers.fake import FakeAuthProvider
from kaleta.auth.providers.local import LocalAuthProvider
from kaleta.auth.providers.supabase import SupabaseAuthProvider
from kaleta.config import settings

__all__ = [
    "AuthProvider",
    "FactorEnrolment",
    "FakeAuthProvider",
    "Identity",
    "LocalAuthProvider",
    "MfaRequired",
    "SignUpResult",
    "SupabaseAuthProvider",
    "get_auth_provider",
    "set_auth_provider",
]

_provider: AuthProvider | None = None


def _build() -> AuthProvider:
    if settings.auth_backend == "supabase":
        if not settings.supabase_url or not settings.supabase_anon_key:
            # The settings validator refuses this combination; kept for a
            # settings object built some other way.
            msg = "KALETA_SUPABASE_URL and KALETA_SUPABASE_ANON_KEY are required"
            raise RuntimeError(msg)
        return SupabaseAuthProvider(
            url=settings.supabase_url,
            anon_key=settings.supabase_anon_key,
            service_role_key=settings.supabase_service_role_key,
            public_url=settings.public_url,
        )
    if settings.auth_backend == "fake":
        # The settings refuse it without KALETA_DEBUG=true.
        return FakeAuthProvider()
    return LocalAuthProvider()


def get_auth_provider() -> AuthProvider:
    """The provider for this process, built on first use."""
    global _provider
    if _provider is None:
        _provider = _build()
    return _provider


def set_auth_provider(provider: AuthProvider | None) -> None:
    """Replace the provider (tests); ``None`` rebuilds it from settings next time."""
    global _provider
    _provider = provider
