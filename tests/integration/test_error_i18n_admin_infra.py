# SPDX-License-Identifier: AGPL-3.0-or-later
"""Admin / infra service domain-error toasts resolve a key (follow-up cohort).

A follow-up slice of ``errors-i18n-message-keys`` covering five hosted / admin /
infra services: ``tenant_service``, ``instance_admin_service``,
``backup_service``, ``nbp_rate_service`` and ``bug_report_service``. Only the
raises whose ``exc.message`` reaches a key-resolving path
(``notify_kaleta_error`` / ``resolve_toast_text``) carry a ``message_key``:

- **tenant_service** (3 of 14): the sign-in / join / invitation raises render
  ``exc.message`` inline in the login / join forms; only the admin-panel-reached
  ``provision`` (e-mail taken), ``resume`` (not suspended) and ``_require_tenant``
  (not found) toast via ``admin._act``.
- **instance_admin_service** (5 of 10): ``for_actor`` is caught by type (404),
  and the CLI-only / UI-gated guards stay English; the family create / delete /
  not-found / reset-login raises toast via ``admin._act``.
- **backup_service** (0 of 8): the Data tab catches a bare ``Exception`` and
  renders ``str(exc)`` inline, so a key would be dead — backup migrates nothing.
- **nbp_rate_service** (all 11): every raise surfaces through the Settings
  "Fetch NBP" button (``data_tab._fetch_nbp`` → ``notify_kaleta_error``).
- **bug_report_service** (3 of 5): the report dialog's submit toasts; ``get`` /
  ``delete`` have no user-facing view.

The cheap, DB-free migrated raises are driven directly; every migrated key is
additionally covered by the both-locales presence and locale-format tables.

Covers: KAL-ERR-009
"""

from __future__ import annotations

import io
import json
import pathlib
import zipfile
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import kaleta.i18n
from kaleta.exceptions import KaletaError, NotFoundError, ValidationError
from kaleta.services import bug_report_service
from kaleta.services.backup_service import BackupService
from kaleta.services.bug_report_service import BugReportService
from kaleta.services.nbp_rate_service import NbpRateService

_LOCALES = pathlib.Path(kaleta.i18n.__file__).parent / "locales"

#: Every migrated admin / infra key, with a representative param set. The
#: locale-format table proves ``str.format`` reproduces each template without a
#: missing-placeholder ``KeyError`` (and the keyless entries pass an empty set).
_ADMIN_INFRA: dict[str, dict[str, object]] = {
    "errors.tenant.email_belongs_to_other_account": {},
    "errors.tenant.not_suspended": {"tenant_id": 7, "status": "deleting"},
    "errors.tenant.not_found": {"tenant_id": 7},
    "errors.instance_admin.not_found": {},
    "errors.instance_admin.family_not_found": {"tenant_id": 7},
    "errors.instance_admin.family_name_required": {},
    "errors.instance_admin.family_name_too_long": {"max": 100},
    "errors.instance_admin.family_name_mismatch": {},
    "errors.instance_admin.login_not_found": {},
    "errors.nbp_rate.timeout": {},
    "errors.nbp_rate.http_error": {"code": 503},
    "errors.nbp_rate.network_unavailable": {},
    "errors.nbp_rate.invalid_json": {},
    "errors.nbp_rate.empty_response": {},
    "errors.nbp_rate.unexpected_shape": {},
    "errors.nbp_rate.missing_effective_date": {},
    "errors.nbp_rate.no_rates": {},
    "errors.nbp_rate.no_usable_rates": {},
    "errors.nbp_rate.invalid_effective_date": {"date": "2026-99-99"},
    "errors.bug_report.field_required": {"field": "Summary"},
    "errors.bug_report.report_not_found": {"report_id": "AB12CD"},
    "errors.bug_report.id_allocation_failed": {},
    "errors.bug_report.rate_limited": {"limit": 5},
}


def _resolve(lang: str, key: str) -> str:
    data: object = json.loads((_LOCALES / f"{lang}.json").read_text(encoding="utf-8"))
    for part in key.split("."):
        assert isinstance(data, dict), (lang, key)
        data = data[part]
    assert isinstance(data, str), (lang, key)
    return data


def _assert_localizes(exc: KaletaError, expected_key: str) -> None:
    """Every migrated raise carries a working key: ``t`` reproduces ``message``.

    A typo in the key or a param name at the raise site breaks this — a missing
    key makes ``t`` echo the key (``!= message``), a wrong param name raises
    ``KeyError`` inside ``format``.
    """
    assert exc.message_key == expected_key
    assert kaleta.i18n.t(exc.message_key, **(exc.params or {})) == exc.message


class TestAdminInfraKeysInterpolate:
    def test_both_locales_carry_every_key(self) -> None:
        for key in _ADMIN_INFRA:
            for lang in ("en", "pl"):
                _resolve(lang, key)  # raises KeyError if the key is missing

    def test_every_key_formats_with_its_params_in_both_locales(self) -> None:
        for key, params in _ADMIN_INFRA.items():
            for lang in ("en", "pl"):
                _resolve(lang, key).format(**params)

    def test_backup_gets_no_block(self) -> None:
        # Backup migrates zero raises (its restore errors render inline), so it
        # deliberately has no ``errors.backup`` block in either locale.
        for lang in ("en", "pl"):
            errors = json.loads((_LOCALES / f"{lang}.json").read_text(encoding="utf-8"))["errors"]
            assert "backup" not in errors


class TestRepresentativeAdminInfraToastReadsInEachLanguage:
    """The representative messages — literals from KAL-ERR-009."""

    def test_polish_empty_response(self) -> None:
        assert _resolve("pl", "errors.nbp_rate.empty_response") == (
            "Odpowiedź NBP (tabela A) była pusta lub nieoczekiwana."
        )

    def test_english_empty_response(self) -> None:
        assert _resolve("en", "errors.nbp_rate.empty_response") == (
            "NBP Table A response was empty or unexpected."
        )

    def test_english_field_required(self) -> None:
        assert _resolve("en", "errors.bug_report.field_required").format(field="Summary") == (
            "Summary is required"
        )

    def test_polish_family_name_too_long_at_100(self) -> None:
        assert _resolve("pl", "errors.instance_admin.family_name_too_long").format(max=100) == (
            "Nazwa rodziny może mieć najwyżej 100 znaków."
        )


class TestMigratedNbpRaisesCarryWorkingKeys:
    """Drive the DB-free NBP raises directly (no session, no HTTP)."""

    def _service(self, body: bytes) -> NbpRateService:
        return NbpRateService(cast(AsyncSession, None), http_get=lambda _url: body)

    def test_invalid_json(self) -> None:
        with pytest.raises(ValidationError) as caught:
            self._service(b"not json").fetch_table_a_payload()
        _assert_localizes(caught.value, "errors.nbp_rate.invalid_json")
        assert caught.value.message == "NBP response was not valid JSON."

    def test_empty_response(self) -> None:
        with pytest.raises(ValidationError) as caught:
            self._service(b"[]").fetch_table_a_payload()
        _assert_localizes(caught.value, "errors.nbp_rate.empty_response")
        assert caught.value.message == "NBP Table A response was empty or unexpected."

    def test_unexpected_shape(self) -> None:
        with pytest.raises(ValidationError) as caught:
            self._service(b"[1, 2]").fetch_table_a_payload()
        _assert_localizes(caught.value, "errors.nbp_rate.unexpected_shape")
        assert caught.value.message == "NBP Table A response had an unexpected shape."

    def test_missing_effective_date(self) -> None:
        with pytest.raises(ValidationError) as caught:
            NbpRateService.parse_mids({})
        _assert_localizes(caught.value, "errors.nbp_rate.missing_effective_date")
        assert caught.value.message == "NBP Table A is missing effectiveDate."

    def test_no_rates(self) -> None:
        with pytest.raises(ValidationError) as caught:
            NbpRateService.parse_mids({"effectiveDate": "2026-01-01", "rates": []})
        _assert_localizes(caught.value, "errors.nbp_rate.no_rates")
        assert caught.value.message == "NBP Table A contained no rates."

    def test_no_usable_rates(self) -> None:
        with pytest.raises(ValidationError) as caught:
            NbpRateService.parse_mids(
                {"effectiveDate": "2026-01-01", "rates": [{"code": "X", "mid": "not-a-number"}]}
            )
        _assert_localizes(caught.value, "errors.nbp_rate.no_usable_rates")
        assert caught.value.message == "NBP Table A contained no usable mid rates."


class TestMigratedBugReportRaiseCarriesWorkingKey:
    def test_blank_summary_is_required(self) -> None:
        with pytest.raises(ValidationError) as caught:
            bug_report_service._required("", field="Summary")
        _assert_localizes(caught.value, "errors.bug_report.field_required")
        assert caught.value.message == "Summary is required"

    async def test_missing_report_not_found(self, session: AsyncSession) -> None:
        # The privacy tab's "my reports" delete reaches ``get`` →
        # ``privacy_tab._remove`` → ``notify_kaleta_error``.
        with pytest.raises(NotFoundError) as caught:
            await BugReportService(session).get("ab12cd")
        _assert_localizes(caught.value, "errors.bug_report.report_not_found")
        assert caught.value.message == "Bug report ab12cd not found"


class TestBackupRaiseStaysEnglish:
    """The deliberate zero-migration decision: backup restore has no key.

    The Data tab (`data_tab._do_restore`) catches a bare ``Exception`` and
    renders ``str(exc)`` inline, never calling ``resolve_toast_text``; a
    ``message_key`` would be dead, so none is added.
    """

    async def test_missing_metadata_restore_has_no_key(self, session: AsyncSession) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("accounts.json", "[]")
        with pytest.raises(ValidationError) as caught:
            await BackupService(session).restore(buf.getvalue())
        assert caught.value.message_key is None
        assert caught.value.message == "Invalid backup: missing metadata.json"
