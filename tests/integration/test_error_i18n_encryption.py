# SPDX-License-Identifier: AGPL-3.0-or-later
"""Encryption / local-identity service domain-error toasts resolve a key.

A follow-up slice of ``errors-i18n-message-keys`` (the first cohort lives in
``test_error_i18n.py``; the transaction, funds, irregular-item, core-CRUD,
household and 2FA cohorts in their own ``test_error_i18n_*`` modules). The
encryption / identity family — ``key_service.py`` and
``local_identity_service.py`` — carries ``message_key`` only on the raises
whose ``exc.message`` reaches a key-resolving path (``notify_kaleta_error`` /
``resolve_toast_text``). The unlock dialogs catch by type or navigate away, the
login / sign-up / change-password forms render ``exc.message`` inline, and only
``data_passphrase_card``, ``delete_account_section`` and the admin panel's
``_act`` route a raise to ``notify_kaleta_error`` (see the plan). Those migrated
toasts render ``t(message_key)`` in the session's language while logs, event
capture and the API keep reading the English ``exc.message`` (see
``KaletaError`` and ``views.error_handling._notify_with_event``).

Real raises are driven directly: ``KeyService.open`` with the tenant frozen in
the key ring (``errors.key.rekeying``), ``LocalIdentityService.set_admin`` on
the sole administrator (``errors.local_identity.last_admin_cannot_demote``), and
``LocalIdentityService.create`` with a malformed e-mail
(``errors.local_identity.email_required`` — the admin "New family" action feeds
``create`` the owner e-mail and surfaces it via ``admin._act`` →
``notify_kaleta_error``). A representative key-less raise these services surface
only inline (``_validate_password``) is asserted to keep its English message
unchanged, documenting the deliberate decision.
Every migrated key is additionally covered by the both-locales presence and
locale-format tables below.

Covers: KAL-ERR-008
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import kaleta.i18n
from kaleta.crypto import key_ring
from kaleta.crypto.keyring import KeyMaterial
from kaleta.db import AsyncSessionFactory
from kaleta.exceptions import ConflictError, KaletaError, ValidationError
from kaleta.services.key_service import KeyService
from kaleta.services.local_identity_service import LocalIdentityService
from kaleta.views.error_handling import resolve_toast_text
from tests.tenancy_helpers import multi_tenant_database

_LOCALES = pathlib.Path(kaleta.i18n.__file__).parent / "locales"

#: Every migrated encryption / local-identity key. None of these raises
#: interpolates params, so every representative param set is empty — the
#: placeholder-format table still proves ``str.format`` is a no-op on each (and
#: would fail on a stray ``{}``).
_ENCRYPTION: dict[str, dict[str, object]] = {
    "errors.key.no_membership": {},
    "errors.key.no_passphrase_set_up": {},
    "errors.key.data_key_not_shared": {},
    "errors.key.rekeying": {},
    "errors.local_identity.email_required": {},
    "errors.local_identity.email_taken": {},
    "errors.local_identity.last_admin_cannot_demote": {},
    "errors.local_identity.last_admin_cannot_disable": {},
    "errors.local_identity.login_not_found": {},
}


def _resolve(lang: str, key: str) -> str:
    data: object = json.loads((_LOCALES / f"{lang}.json").read_text(encoding="utf-8"))
    for part in key.split("."):
        assert isinstance(data, dict), (lang, key)
        data = data[part]
    assert isinstance(data, str), (lang, key)
    return data


class TestEncryptionKeysInterpolate:
    def test_both_locales_carry_every_encryption_key(self) -> None:
        for key in _ENCRYPTION:
            for lang in ("en", "pl"):
                _resolve(lang, key)  # raises KeyError if the key is missing

    def test_every_key_formats_with_its_params_in_both_locales(self) -> None:
        for key, params in _ENCRYPTION.items():
            for lang in ("en", "pl"):
                _resolve(lang, key).format(**params)


class TestRepresentativeEncryptionToastReadsInEachLanguage:
    """The representative errors — literals from KAL-ERR-008."""

    def test_polish_last_admin_message(self) -> None:
        assert _resolve("pl", "errors.local_identity.last_admin_cannot_demote") == (
            "Ostatni administrator nie może przestać nim być."
        )

    def test_english_last_admin_message(self) -> None:
        assert _resolve("en", "errors.local_identity.last_admin_cannot_demote") == (
            "The last administrator cannot stop being one."
        )

    def test_polish_rekeying_message(self) -> None:
        assert _resolve("pl", "errors.key.rekeying") == (
            "Twoje gospodarstwo jest w trakcie zmiany kluczy. Spróbuj ponownie za chwilę."
        )


def _assert_localizes(exc: KaletaError, expected_key: str) -> None:
    """Every migrated raise carries a working key: ``t`` reproduces ``message``.

    A typo in the key or a param name at the raise site breaks this — a missing
    key makes ``t`` echo the key (``!= message``), and a wrong param name raises
    ``KeyError`` inside ``format``.
    """
    assert exc.message_key == expected_key
    assert kaleta.i18n.t(exc.message_key, **(exc.params or {})) == exc.message


@dataclass
class _FrozenStore:
    """A minimal ``KeyStore`` whose block is set up — enough to reach the freeze check.

    ``KeyService.open`` reads ``load()`` and ``tenant_id`` before any crypto or
    DB work, so a block with ``dek_sealed`` set lets the ``is_frozen`` guard
    fire without a real keypair or session.
    """

    tenant_id: int
    member_ref: str = "local:1@1"

    async def load(self) -> KeyMaterial:
        return KeyMaterial(
            public_key=b"pub",
            private_key_wrapped=b"wrapped",
            private_key_salt=b"salt",
            kdf_params="{}",
            dek_sealed=b"sealed",
        )

    async def save(self, material: KeyMaterial) -> None:  # pragma: no cover - not reached
        raise AssertionError

    async def key_version(self) -> int:  # pragma: no cover - not reached
        return 1

    async def creates_the_data_key(self) -> bool:  # pragma: no cover - not reached
        return False


class TestMigratedEncryptionRaisesCarryWorkingKeys:
    """Drive one real raise from each migrated service."""

    async def test_open_while_frozen_carries_the_rekeying_key(self) -> None:
        # A unique tenant id, frozen in the key ring: ``open`` refuses before
        # it touches a session. Thaw in ``finally`` so no state leaks.
        tenant_id = 987_654_321
        service = KeyService(
            _FrozenStore(tenant_id=tenant_id),  # type: ignore[arg-type]
            None,  # type: ignore[arg-type]  # the freeze guard raises before any DB use
        )
        key_ring.freeze(tenant_id)
        try:
            with pytest.raises(ConflictError) as caught:
                await service.open("whatever")
        finally:
            key_ring.thaw(tenant_id)
        _assert_localizes(caught.value, "errors.key.rekeying")
        assert caught.value.message == "Your household is being re-keyed. Try again in a moment."

    async def test_demoting_the_sole_admin_carries_its_key(self, instance: str) -> None:
        # One administrator on a clean instance: demoting them is refused.
        async with AsyncSessionFactory.public() as public:
            logins = LocalIdentityService(public)
            admin = await logins.create("admin@example.com", "correct horse battery", admin=True)
            with pytest.raises(ValidationError) as caught:
                await logins.set_admin(admin.id, False)
        _assert_localizes(caught.value, "errors.local_identity.last_admin_cannot_demote")
        assert caught.value.message == "The last administrator cannot stop being one."

    async def test_creating_a_login_with_a_blank_email_carries_its_key(
        self, session: AsyncSession
    ) -> None:
        # The admin "New family" action calls LocalIdentityService.create with
        # the owner e-mail the admin typed; a malformed one raises before any
        # write. (``create`` is validation-first, so the shared session is not
        # mutated.) This is the key_resolving path via admin._act.
        with pytest.raises(ValidationError) as caught:
            await LocalIdentityService(session).create("not-an-email", "correct horse battery")
        _assert_localizes(caught.value, "errors.local_identity.email_required")
        assert caught.value.message == "Enter an e-mail address."


class TestKeylessRaiseStaysEnglish:
    """The deliberate decision: a raise surfaced only inline keeps English.

    ``_validate_password`` is reached only through the login / sign-up /
    change-password forms, which render ``exc.message`` inline (``_say``); a
    ``message_key`` there would be a dead key, so none is added and the toast
    text falls back to the English ``exc.message`` unchanged.
    """

    def test_too_short_password_has_no_key_and_renders_english(self) -> None:
        with pytest.raises(ValidationError) as caught:
            LocalIdentityService._validate_password("short")
        assert caught.value.message_key is None
        assert resolve_toast_text(caught.value) == caught.value.message
        assert caught.value.message == "Password must be at least 8 characters."


@pytest.fixture
async def instance() -> AsyncIterator[str]:
    """A clean ``auth_backend=local`` registry, its own schema and session factory."""
    async with multi_tenant_database(auth_backend="local") as url:
        yield url
