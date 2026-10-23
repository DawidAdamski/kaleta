# SPDX-License-Identifier: AGPL-3.0-or-later
"""Two-factor / API-token service domain-error toasts resolve a translation key.

A follow-up slice of ``errors-i18n-message-keys`` (the first cohort lives in
``test_error_i18n.py``; the transaction, funds, irregular-item, core-CRUD and
household cohorts in their own ``test_error_i18n_*`` modules). The 2FA family —
``MfaService``, ``HostedMfaService`` and ``ApiTokenService`` — carries
``message_key`` only on the raises whose ``exc.message`` reaches a
key-resolving path (``notify_kaleta_error`` / ``resolve_toast_text``); the
dialogs swallow the rest by type, substituting their own localized keys, and
the inline ``error.set_text(exc.message)`` paths never resolve a key (see the
plan). Those migrated toasts render ``t(message_key)`` in the session's
language while logs, event capture and the API keep reading the English
``exc.message`` (see ``KaletaError`` and
``views.error_handling._notify_with_event``). ``HostedMfaService`` has no raise
on a key-resolving path, so none of its raises is migrated.

One real raise is driven per migrated service: ``_require_step_up`` via
``ApiTokenService.create_token`` and ``MfaService.regenerate_recovery_codes``
with the factor off. Every migrated key is additionally covered by the
both-locales presence and locale-format tables below.

Covers: KAL-ERR-007
"""

from __future__ import annotations

import json
import pathlib
import time

import pyotp
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import kaleta.i18n
from kaleta.exceptions import KaletaError, ValidationError
from kaleta.models.user import User
from kaleta.services.api_token_service import ApiTokenService
from kaleta.services.mfa_service import TOTP_INTERVAL, MfaService

_LOCALES = pathlib.Path(kaleta.i18n.__file__).parent / "locales"

#: Every migrated 2FA key. None of these raises interpolates params, so every
#: representative param set is empty — the placeholder-format table still
#: proves ``str.format`` is a no-op on each (and would fail on a stray ``{}``).
_2FA: dict[str, dict[str, object]] = {
    "errors.mfa.user_not_found": {},
    "errors.mfa.enable_before_recovery_codes": {},
    "errors.mfa.confirm_before_recovery_codes": {},
    "errors.api_token.confirm_code_before_changing": {},
}


def _resolve(lang: str, key: str) -> str:
    data: object = json.loads((_LOCALES / f"{lang}.json").read_text(encoding="utf-8"))
    for part in key.split("."):
        assert isinstance(data, dict), (lang, key)
        data = data[part]
    assert isinstance(data, str), (lang, key)
    return data


class Test2faKeysInterpolate:
    def test_both_locales_carry_every_2fa_key(self) -> None:
        for key in _2FA:
            for lang in ("en", "pl"):
                _resolve(lang, key)  # raises KeyError if the key is missing

    def test_every_key_formats_with_its_params_in_both_locales(self) -> None:
        for key, params in _2FA.items():
            for lang in ("en", "pl"):
                _resolve(lang, key).format(**params)


class TestRepresentative2faToastReadsInEachLanguage:
    """The representative 2FA errors — literals from KAL-ERR-007."""

    def test_polish_mfa_message(self) -> None:
        assert _resolve("pl", "errors.mfa.enable_before_recovery_codes") == (
            "Włącz uwierzytelnianie dwuskładnikowe, zanim poprosisz o kody zapasowe."
        )

    def test_english_mfa_message(self) -> None:
        assert _resolve("en", "errors.mfa.enable_before_recovery_codes") == (
            "Enable two-factor authentication before asking for recovery codes."
        )

    def test_polish_api_token_message(self) -> None:
        assert _resolve("pl", "errors.api_token.confirm_code_before_changing") == (
            "Potwierdź kodem uwierzytelniania dwuskładnikowego, zanim zmienisz tokeny API."
        )


def _assert_localizes(exc: KaletaError, expected_key: str) -> None:
    """Every migrated raise carries a working key: ``t`` reproduces ``message``.

    A typo in the key or a param name at the raise site breaks this — a missing
    key makes ``t`` echo the key (``!= message``), and a wrong param name raises
    ``KeyError`` inside ``format``.
    """
    assert exc.message_key == expected_key
    assert kaleta.i18n.t(exc.message_key, **(exc.params or {})) == exc.message


@pytest.fixture
def user(suite_owner: User) -> User:
    return suite_owner


async def _enrol(session: AsyncSession, user_id: int) -> None:
    mfa = MfaService(session)
    enrolment = await mfa.begin_enrolment(user_id)
    code = pyotp.TOTP(enrolment.secret, interval=TOTP_INTERVAL).at(int(time.time()))
    await mfa.confirm_enrolment(user_id, str(code))


class TestMigrated2faRaisesCarryWorkingKeys:
    """Drive one real raise from each migrated service against the DB."""

    @pytest.mark.asyncio
    async def test_api_token_step_up_carries_its_key(
        self, session: AsyncSession, user: User
    ) -> None:
        # Factor on, no fresh code → minting a token raises the step-up error.
        await _enrol(session, user.id)
        with pytest.raises(ValidationError) as caught:
            await ApiTokenService(session).create_token(user_id=user.id, label="ci")
        _assert_localizes(caught.value, "errors.api_token.confirm_code_before_changing")
        assert caught.value.message == (
            "Confirm with a two-factor code before changing API tokens."
        )

    @pytest.mark.asyncio
    async def test_regenerate_with_factor_off_carries_its_key(
        self, session: AsyncSession, user: User
    ) -> None:
        # No factor enrolled → reissuing recovery codes is refused.
        with pytest.raises(ValidationError) as caught:
            await MfaService(session).regenerate_recovery_codes(user.id)
        _assert_localizes(caught.value, "errors.mfa.enable_before_recovery_codes")
        assert caught.value.message == (
            "Enable two-factor authentication before asking for recovery codes."
        )
