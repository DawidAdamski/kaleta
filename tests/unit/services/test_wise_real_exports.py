# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parse real-world Wise export shapes from anonymized dogfood fixtures."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from kaleta.services.import_profiles import MBANK_PROFILE, WISE_PROFILE, detect_bank_profile
from kaleta.services.import_service import ImportService, WisePreprocessor

FIXTURES = Path(__file__).resolve().parents[2] / "e2e" / "fixtures" / "import" / "wise"


class _NoSession:
    session = None


def test_dogfood_fixture_auto_detects_and_parses() -> None:
    content = (FIXTURES / "jpy-travel-sample.csv").read_text(encoding="utf-8")
    assert detect_bank_profile(content) == WISE_PROFILE
    meta = WisePreprocessor.extract_metadata(content)
    assert meta.currency == "JPY"
    assert meta.account_type == "Wise"
    assert meta.date_from is not None
    assert meta.date_to is not None

    result = ImportService(_NoSession()).parse_queued_file(content, "generic")  # type: ignore[arg-type]
    assert result.ok is True
    assert result.profile == WISE_PROFILE
    assert result.metadata is not None
    assert len(result.rows) == 9


def test_wise_fixture_uses_merchant_as_description() -> None:
    content = (FIXTURES / "jpy-travel-sample.csv").read_text(encoding="utf-8")
    result = ImportService(_NoSession()).parse_queued_file(content, WISE_PROFILE)  # type: ignore[arg-type]
    assert result.rows is not None
    card_row = next(r for r in result.rows if r.amount == Decimal("-51571"))
    assert card_row.description == "Japanpost Bank(245950) GIFU"
    assert "Transakcja kartą" not in card_row.description


def test_wise_fixture_parses_top_up_as_income() -> None:
    content = (FIXTURES / "jpy-travel-sample.csv").read_text(encoding="utf-8")
    result = ImportService(_NoSession()).parse_queued_file(content, WISE_PROFILE)  # type: ignore[arg-type]
    assert result.rows is not None
    top_up = next(r for r in result.rows if r.amount == Decimal("100000"))
    assert top_up.description == "Doładowanie konta"


@pytest.mark.parametrize(
    "profile",
    [WISE_PROFILE, "generic"],
)
def test_wise_not_confused_with_mbank(profile: str) -> None:
    content = (FIXTURES / "jpy-travel-sample.csv").read_text(encoding="utf-8")
    result = ImportService(_NoSession()).parse_queued_file(content, profile)  # type: ignore[arg-type]
    assert result.profile == WISE_PROFILE
    assert result.profile != MBANK_PROFILE
