# SPDX-License-Identifier: AGPL-3.0-or-later
"""Long-tail service domain-error toasts resolve a key (final cohort).

The final slice of ``errors-i18n-message-keys``, mopping up the remaining
services that still had plain-English ``KaletaError`` raises reaching a toast.
Only the raises whose ``exc.message`` reaches a key-resolving path
(``notify_kaleta_error`` / ``resolve_toast_text``) carry a ``message_key``:

- **import_rule_service** (4 of 4): the Settings → Import rule-edit dialog wraps
  ``update`` in ``except KaletaError: notify_kaleta_error``, so not-found,
  account-not-found and both pattern guards toast.
- **annual_review_service** (2 of 3): ``adjust`` / ``drop`` toast via the review
  panel; ``carry`` has no ``except`` arm (and its guard is UI-unreachable).
- **unplanned_radar_service** (2 of 2): the wizard promote dialog toasts.
- **planned_transaction_service** (2 of 2): the payment-calendar / planned
  views toast ``_ensure_posted`` and the deliberate post-commit
  ``ConflictError``.
- **planned_price_drift_service** (2 of 2): the price-drift accept toasts.
- **account_deletion_service** (1 of 1): the settings delete-account flow toasts.

The DEAD services (``category_template``, ``saved_report``, ``report_columns``,
``monthly_readiness``, ``institution_logo``, ``audit``) render inline, catch by
type, or have no toast arm; ``scenario_service`` / ``forecast_service`` raise
nothing. The cheap, DB-free migrated raises are driven directly; every migrated
key is additionally covered by the both-locales presence and locale-format
tables.

Covers: KAL-ERR-010
"""

from __future__ import annotations

import datetime
import json
import pathlib
from decimal import Decimal
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import kaleta.i18n
from kaleta.exceptions import KaletaError, ValidationError
from kaleta.models.planned_transaction import RecurrenceFrequency
from kaleta.schemas.unplanned_radar import RadarCandidate
from kaleta.services.planned_price_drift_service import PlannedPriceDriftService
from kaleta.services.saved_report_service import ReportConfig, SavedReportService
from kaleta.services.unplanned_radar_service import UnplannedRadarService

_LOCALES = pathlib.Path(kaleta.i18n.__file__).parent / "locales"

#: Every migrated long-tail key, with a representative param set. The
#: locale-format table proves ``str.format`` reproduces each template without a
#: missing-placeholder ``KeyError`` (and the keyless entries pass an empty set).
_LONG_TAIL: dict[str, dict[str, object]] = {
    "errors.import_rule.not_found": {"rule_id": 7},
    "errors.import_rule.account_not_found": {"account_id": 3},
    "errors.import_rule.pattern_empty": {},
    "errors.import_rule.pattern_too_long": {},
    "errors.annual_review.subscription_not_found": {"commitment_id": 42},
    "errors.unplanned_radar.name_required": {},
    "errors.unplanned_radar.amount_not_positive": {},
    "errors.planned_transaction.posted_rows_missing": {"missing": [11, 12]},
    "errors.planned_transaction.not_found": {"planned_id": 9},
    "errors.planned_price_drift.positive_amount": {},
    "errors.planned_price_drift.not_found": {"planned_id": 9},
    "errors.account_deletion.tenant_not_found": {"tenant_id": 5},
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


def _candidate(*, source_name: str, typical_amount: Decimal) -> RadarCandidate:
    """A minimal radar candidate — only ``source_name`` / ``typical_amount`` are
    read before ``create_planned_from_candidate`` raises its input guards."""
    today = datetime.date(2026, 1, 1)
    return RadarCandidate(
        payee_id=None,
        source_name=source_name,
        typical_amount=typical_amount,
        occurrences=3,
        first_seen_at=today,
        last_seen_at=today,
        average_gap_days=120,
        next_expected_at=today,
        frequency=RecurrenceFrequency.YEARLY,
        interval=1,
        yearly_estimate=typical_amount,
        account_id=1,
        category_id=None,
        occurrence_dates=[today],
        transaction_ids=[1, 2, 3],
    )


class TestLongTailKeysInterpolate:
    def test_both_locales_carry_every_key(self) -> None:
        for key in _LONG_TAIL:
            for lang in ("en", "pl"):
                _resolve(lang, key)  # raises KeyError if the key is missing

    def test_every_key_formats_with_its_params_in_both_locales(self) -> None:
        for key, params in _LONG_TAIL.items():
            for lang in ("en", "pl"):
                _resolve(lang, key).format(**params)


class TestRepresentativeLongTailToastReadsInEachLanguage:
    """The representative messages — literals from KAL-ERR-010."""

    def test_polish_name_required(self) -> None:
        assert _resolve("pl", "errors.unplanned_radar.name_required") == (
            "Transakcja planowana wymaga nazwy."
        )

    def test_english_name_required(self) -> None:
        assert _resolve("en", "errors.unplanned_radar.name_required") == (
            "A planned transaction needs a name"
        )

    def test_polish_import_rule_not_found_at_7(self) -> None:
        assert _resolve("pl", "errors.import_rule.not_found").format(rule_id=7) == (
            "Nie znaleziono reguły importu 7."
        )


class TestMigratedRaisesCarryWorkingKeys:
    """Drive the DB-free migrated raises directly (the guards fire before any I/O)."""

    async def test_unplanned_radar_name_required(self) -> None:
        service = UnplannedRadarService(cast(AsyncSession, None))
        with pytest.raises(ValidationError) as caught:
            await service.create_planned_from_candidate(
                _candidate(source_name="", typical_amount=Decimal("10.00")), name=""
            )
        _assert_localizes(caught.value, "errors.unplanned_radar.name_required")
        assert caught.value.message == "A planned transaction needs a name"

    async def test_unplanned_radar_amount_not_positive(self) -> None:
        service = UnplannedRadarService(cast(AsyncSession, None))
        with pytest.raises(ValidationError) as caught:
            await service.create_planned_from_candidate(
                _candidate(source_name="Dentist", typical_amount=Decimal("0.00"))
            )
        _assert_localizes(caught.value, "errors.unplanned_radar.amount_not_positive")
        assert caught.value.message == "A planned transaction needs a positive amount"

    async def test_planned_price_drift_positive_amount(self) -> None:
        service = PlannedPriceDriftService(cast(AsyncSession, None))
        with pytest.raises(ValidationError) as caught:
            await service.accept(1, Decimal("0"))
        _assert_localizes(caught.value, "errors.planned_price_drift.positive_amount")
        assert caught.value.message == "A planned transaction needs a positive amount"


class TestDeadReportsRaiseStaysEnglish:
    """The deliberate zero-migration decision for the inline Reports path.

    ``views/reports/page.py`` catches a bare ``Exception`` and renders
    ``str(exc)`` inline in the chart zone, never calling ``resolve_toast_text``;
    a ``message_key`` would be dead, so none is added.
    """

    async def test_same_dimension_twice_has_no_key(self) -> None:
        service = SavedReportService(cast(AsyncSession, None))
        with pytest.raises(ValidationError) as caught:
            await service.execute(ReportConfig(dimension="category", series="category"))
        assert caught.value.message_key is None
        assert caught.value.message == "A report cannot be grouped by the same dimension twice."
