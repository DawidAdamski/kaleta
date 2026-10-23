# SPDX-License-Identifier: AGPL-3.0-or-later
"""Domain-error toasts resolve a translation key, so they speak the user's language.

A migrated raise site carries ``message_key`` + ``params``; the view renders
``t(message_key, **params)`` for the toast while logs, event capture and the
API keep reading the English ``exc.message`` (see ``KaletaError`` and
``views.error_handling._notify_with_event``). This anchors the first cohort
(payee identity / merge-undo) by checking the keys exist in both locales and
interpolate their parameters the same way ``t`` does (``str.format``).

Covers: KAL-ERR-001
"""

from __future__ import annotations

import datetime
import json
import pathlib

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import kaleta.i18n
from kaleta.exceptions import ConflictError, KaletaError, NotFoundError
from kaleta.schemas.payee import PayeeCreate
from kaleta.schemas.payee_identity import PayeeIdentityCreate
from kaleta.services.payee_merge_service import UNDO_WINDOW, PayeeMergeService
from kaleta.services.payee_service import PayeeService
from kaleta.views.error_handling import resolve_toast_text

_LOCALES = pathlib.Path(kaleta.i18n.__file__).parent / "locales"

#: The first-cohort keys with a representative set of params for each — the
#: placeholder names must match what the raise sites pass.
_FIRST_COHORT: dict[str, dict[str, object]] = {
    "errors.payee.identity_taken": {"pattern": "lidl poznan", "owner": "Lidl sp z o o"},
    "errors.payee.identity_already_owned": {"pattern": "LIDL POZNAN"},
    "errors.payee.merge_not_found": {},
    "errors.payee.merge_undo_expired": {"days": 7},
    "errors.payee.name_exists": {"name": "Rossmann"},
}


def _resolve(lang: str, key: str) -> str:
    data: object = json.loads((_LOCALES / f"{lang}.json").read_text(encoding="utf-8"))
    for part in key.split("."):
        assert isinstance(data, dict), (lang, key)
        data = data[part]
    assert isinstance(data, str), (lang, key)
    return data


class TestFirstCohortKeysInterpolate:
    def test_both_locales_carry_every_first_cohort_key(self) -> None:
        for key in _FIRST_COHORT:
            for lang in ("en", "pl"):
                _resolve(lang, key)  # raises KeyError if the key is missing

    def test_every_key_formats_with_its_params_in_both_locales(self) -> None:
        # ``t`` interpolates via ``str.format(**params)``; a missing placeholder
        # would raise KeyError here, which is exactly what we guard against.
        for key, params in _FIRST_COHORT.items():
            for lang in ("en", "pl"):
                _resolve(lang, key).format(**params)


#: The representative payee-identity conflict params — literals from KAL-ERR-001.
_IDENTITY_PARAMS = {"pattern": "lidl poznan", "owner": "Lidl sp z o o"}


class TestIdentityTakenToastReadsInEachLanguage:
    """The representative payee-identity conflict — literals from KAL-ERR-001."""

    def test_polish_message(self) -> None:
        text = _resolve("pl", "errors.payee.identity_taken").format(**_IDENTITY_PARAMS)
        assert text == "„lidl poznan” jest już wariantem nazwy odbiorcy „Lidl sp z o o”"

    def test_english_message(self) -> None:
        text = _resolve("en", "errors.payee.identity_taken").format(**_IDENTITY_PARAMS)
        assert text == "'lidl poznan' is already an identity of payee 'Lidl sp z o o'"

    def test_english_key_reproduces_the_untranslated_fallback(self) -> None:
        # The migrated raise keeps the same English message as its fallback, so
        # resolving the key must yield exactly the old free-text string.
        fallback = (
            f"'{_IDENTITY_PARAMS['pattern']}' is already an identity "
            f"of payee '{_IDENTITY_PARAMS['owner']}'"
        )
        assert _resolve("en", "errors.payee.identity_taken").format(**_IDENTITY_PARAMS) == fallback


class TestCarrierStoresKeyAndParams:
    """The migrated raise sites pass the key/params through ``KaletaError``."""

    def test_conflict_error_exposes_message_key_and_params(self) -> None:
        exc = ConflictError(
            "'lidl poznan' is already an identity of payee 'Lidl sp z o o'",
            message_key="errors.payee.identity_taken",
            params={"pattern": "lidl poznan", "owner": "Lidl sp z o o"},
        )
        assert exc.message_key == "errors.payee.identity_taken"
        assert exc.params == {"pattern": "lidl poznan", "owner": "Lidl sp z o o"}
        # The English message is untouched — logs and the API still read it.
        assert exc.message == "'lidl poznan' is already an identity of payee 'Lidl sp z o o'"
        assert exc.code == "conflict"

    def test_message_key_and_params_default_to_none(self) -> None:
        exc = ConflictError("plain message")
        assert exc.message_key is None
        assert exc.params is None


class TestResolveToastText:
    """The view's key-or-fallback selection, isolated from NiceGUI."""

    def test_an_un_migrated_error_falls_back_to_its_english_message(self) -> None:
        exc = ConflictError("plain English message")
        assert resolve_toast_text(exc) == "plain English message"

    def test_a_migrated_error_resolves_its_key(self) -> None:
        # No NiceGUI session in a test, so ``t`` resolves against English and
        # the first-cohort key reproduces the English fallback exactly.
        exc = ConflictError(
            "ignored fallback",
            message_key="errors.payee.identity_taken",
            params={"pattern": "lidl poznan", "owner": "Lidl sp z o o"},
        )
        assert resolve_toast_text(exc) == (
            "'lidl poznan' is already an identity of payee 'Lidl sp z o o'"
        )


def _assert_localizes(exc: KaletaError, expected_key: str) -> None:
    """Every migrated raise carries a working key: ``t`` must reproduce ``message``.

    A typo in the key or a param name at the raise site breaks this — a missing
    key makes ``t`` echo the key (``!= message``), and a wrong param name raises
    ``KeyError`` inside ``format``. This is the check the locale-format table
    above cannot do, because it hand-copies the params instead of reading them
    off the raise site.
    """
    assert exc.message_key == expected_key
    assert kaleta.i18n.t(exc.message_key, **(exc.params or {})) == exc.message


class TestMigratedRaiseSitesCarryWorkingKeys:
    """Drive the real first-cohort raises and resolve their keys for real."""

    async def test_identity_conflicts_carry_their_keys(self, session: AsyncSession) -> None:
        payees = PayeeService(session)
        lidl = await payees.create(PayeeCreate(name="Lidl sp z o o"))
        kaufland = await payees.create(PayeeCreate(name="Kaufland"))
        await payees.add_identity(lidl.id, PayeeIdentityCreate(pattern="LIDL POZNAN"))

        with pytest.raises(ConflictError) as taken:
            await payees.add_identity(kaufland.id, PayeeIdentityCreate(pattern="lidl poznan"))
        _assert_localizes(taken.value, "errors.payee.identity_taken")

        with pytest.raises(ConflictError) as owned:
            await payees.add_identity(lidl.id, PayeeIdentityCreate(pattern="lidl poznan"))
        _assert_localizes(owned.value, "errors.payee.identity_already_owned")

    async def test_merge_undo_errors_carry_their_keys(self, session: AsyncSession) -> None:
        merge_svc = PayeeMergeService(session)

        with pytest.raises(NotFoundError) as missing:
            await merge_svc.undo(999_999)
        _assert_localizes(missing.value, "errors.payee.merge_not_found")

        # A real auto-merge record, so undo reaches the window and clash guards.
        payees = PayeeService(session)
        keeper = await payees.create(PayeeCreate(name="Rossmann Drogeria 12"))
        other = await payees.create(PayeeCreate(name="Rossmann Drogeria 13"))
        record = (await merge_svc.scan(auto_merge_threshold=0.92)).merged[0]
        assert (record.merged_name, record.keeper_id) == ("Rossmann Drogeria 13", keeper.id)
        assert other.id  # merged away by the scan

        later = record.merged_at + UNDO_WINDOW + datetime.timedelta(days=1)
        with pytest.raises(ConflictError) as expired:
            await merge_svc.undo(record.id, now=later)
        _assert_localizes(expired.value, "errors.payee.merge_undo_expired")

        # A fresh payee holding the merged name makes undo clash on restore.
        await payees.create(PayeeCreate(name="Rossmann Drogeria 13"))
        with pytest.raises(ConflictError) as clash:
            await merge_svc.undo(record.id)
        _assert_localizes(clash.value, "errors.payee.name_exists")
