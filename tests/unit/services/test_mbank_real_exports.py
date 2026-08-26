# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parse real-world mBank export shapes from anonymized dogfood fixtures."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from kaleta.services.import_profiles import MBANK_PROFILE, detect_bank_profile
from kaleta.services.import_service import (
    ImportService,
    MBankPreprocessor,
    auto_decode,
    counterparty_account_raw,
    digits_only,
    is_counterparty_transfer,
)

FIXTURES = Path(__file__).resolve().parents[2] / "e2e" / "fixtures" / "import" / "mbank"


class _NoSession:
    session = None


@pytest.mark.parametrize(
    "filename",
    ["credit-card-sample.csv", "current-account-sample.csv"],
)
def test_dogfood_fixture_auto_detects_and_parses(filename: str) -> None:
    content = (FIXTURES / filename).read_text(encoding="utf-8")
    assert detect_bank_profile(content) == MBANK_PROFILE
    meta = MBankPreprocessor.extract_metadata(content)
    assert meta.currency == "PLN"
    assert meta.account_number_digits

    result = ImportService(_NoSession()).parse_queued_file(content, "generic")  # type: ignore[arg-type]
    assert result.ok is True
    assert result.profile == MBANK_PROFILE
    assert result.metadata is not None
    assert len(result.rows) >= 10


def test_credit_card_fixture_parses_card_purchases() -> None:
    content = (FIXTURES / "credit-card-sample.csv").read_text(encoding="utf-8")
    result = ImportService(_NoSession()).parse_queued_file(content, MBANK_PROFILE)  # type: ignore[arg-type]
    assert result.rows is not None
    negatives = [r for r in result.rows if r.amount < 0]
    assert negatives
    assert any(
        "DISNEY" in r.description.upper() or "KARTY" in r.description.upper() for r in result.rows
    )


def test_current_account_fixture_parses_transfer_counterparty() -> None:
    content = (FIXTURES / "current-account-sample.csv").read_text(encoding="utf-8")
    result = ImportService(_NoSession()).parse_queued_file(content, MBANK_PROFILE)  # type: ignore[arg-type]
    assert result.rows is not None
    with_counterparty = [r for r in result.rows if digits_only(counterparty_account_raw(r.raw))]
    assert with_counterparty
    row = next(
        r
        for r in with_counterparty
        if digits_only(counterparty_account_raw(r.raw)) == "96132015374150799939999901"
    )
    known = {digits_only(counterparty_account_raw(row.raw))}
    assert is_counterparty_transfer(row, known)


def test_cp1250_bytes_decode_and_parse() -> None:
    raw = (FIXTURES / "current-account-sample.csv").read_bytes()
    content = auto_decode(raw)
    result = ImportService(_NoSession()).parse_queued_file(content, MBANK_PROFILE)  # type: ignore[arg-type]
    assert result.ok is True
    assert result.rows
    assert result.rows[0].date.isoformat() == "2019-06-12"


def test_polish_amount_with_spaces_parses() -> None:
    content = (FIXTURES / "current-account-sample.csv").read_text(encoding="utf-8")
    result = ImportService(_NoSession()).parse_queued_file(content, MBANK_PROFILE)  # type: ignore[arg-type]
    assert result.rows is not None
    incoming = next(r for r in result.rows if r.amount == Decimal("1000.00"))
    assert incoming.description
