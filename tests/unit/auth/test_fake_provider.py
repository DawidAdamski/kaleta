# SPDX-License-Identifier: AGPL-3.0-or-later
"""``KALETA_AUTH_BACKEND=fake`` — the debug stand-in for Supabase Auth.

Covers: KAL-TEN-011
"""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from kaleta.auth.providers import FakeAuthProvider
from kaleta.exceptions import ConflictError, UnauthorizedError, ValidationError


@pytest.fixture
def store(tmp_path: Path) -> Path:
    return tmp_path / "fake-auth.json"


async def test_sign_up_is_confirmed_at_once_and_signs_in(store: Path) -> None:
    """Covers: KAL-TEN-011"""
    provider = FakeAuthProvider(store)

    result = await provider.sign_up(" Ania@Example.com ", "correct-horse")

    assert result.needs_verification is False
    assert result.identity is not None
    assert result.identity.email == "ania@example.com"
    assert result.identity.email_verified is True
    signed_in = await provider.sign_in("ania@example.com", "correct-horse")
    assert signed_in == result.identity


async def test_identities_survive_a_new_process(store: Path) -> None:
    """A restarted container still knows who signed up — same subject, same account."""
    first = await FakeAuthProvider(store).sign_up("ania@example.com", "correct-horse")

    again = await FakeAuthProvider(store).sign_in("ania@example.com", "correct-horse")

    assert first.identity is not None
    assert again == first.identity


async def test_the_store_holds_a_hash_not_the_password_and_is_owner_only(store: Path) -> None:
    await FakeAuthProvider(store).sign_up("ania@example.com", "correct-horse")

    raw = store.read_text(encoding="utf-8")
    assert "correct-horse" not in raw
    assert json.loads(raw)["ania@example.com"]["password_hash"].startswith("$argon2")
    assert stat.S_IMODE(store.stat().st_mode) == 0o600


async def test_a_wrong_password_or_unknown_address_is_refused(store: Path) -> None:
    provider = FakeAuthProvider(store)
    await provider.sign_up("ania@example.com", "correct-horse")

    with pytest.raises(UnauthorizedError):
        await provider.sign_in("ania@example.com", "wrong-horse")
    with pytest.raises(UnauthorizedError):
        await provider.sign_in("nobody@example.com", "correct-horse")


async def test_signing_up_twice_is_a_conflict(store: Path) -> None:
    provider = FakeAuthProvider(store)
    await provider.sign_up("ania@example.com", "correct-horse")

    with pytest.raises(ConflictError):
        await provider.sign_up("ANIA@example.com", "another-horse")


async def test_delete_identity_forgets_the_address(store: Path) -> None:
    """Covers: KAL-TEN-011"""
    provider = FakeAuthProvider(store)
    result = await provider.sign_up("ania@example.com", "correct-horse")
    assert result.identity is not None

    await provider.delete_identity(result.identity.subject)
    await provider.delete_identity(result.identity.subject)  # already gone: no error

    with pytest.raises(UnauthorizedError):
        await provider.sign_in("ania@example.com", "correct-horse")


async def test_mail_and_second_factor_flows_say_they_do_not_exist(store: Path) -> None:
    provider = FakeAuthProvider(store)

    with pytest.raises(ValidationError, match="sends no e-mail"):
        await provider.request_password_reset("ania@example.com")
    with pytest.raises(ValidationError, match="sends no e-mail"):
        await provider.request_magic_link("ania@example.com")
    with pytest.raises(ValidationError, match="no second factor"):
        await provider.mfa_unenrol("subject", "factor")
