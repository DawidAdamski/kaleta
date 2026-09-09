# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parse the Wise QIF statement export shape from the anonymized dogfood fixture.

The fixture is a real Wise export with only the card-holder memos anonymized,
so expected values are literals read off ``jpy-travel-sample.qif`` itself. The
QIF says less than the CSV — no currency in the body, and a memo that names the
card rather than the transaction — so nothing here may be borrowed from the CSV
fixture or computed by the parser under test.

The fixture is stored under a hand-given name; the name Wise actually downloads
it as is ``WISE_QIF_NAME`` below, taken from the provenance note in
``tests/e2e/fixtures/import/wise/NOTES.md``.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from kaleta.services.import_profiles import (
    GENERIC_PROFILE,
    MBANK_PROFILE,
    WISE_PROFILE,
    detect_bank_profile,
    is_wise_content,
    is_wise_qif_content,
)
from kaleta.services.import_service import (
    ImportService,
    WiseQifPreprocessor,
    iter_qif_records,
)

FIXTURES = Path(__file__).resolve().parents[2] / "e2e" / "fixtures" / "import" / "wise"
QIF_FIXTURE = FIXTURES / "jpy-travel-sample.qif"

# The shape Wise gives every statement download — the only place the export
# names its currency. The account-id segment is anonymized, as in the fixtures.
WISE_QIF_NAME = "statement_12345678_JPY_2026-04-01_2026-06-30.qif"


class _NoSession:
    session = None


def _content() -> str:
    return QIF_FIXTURE.read_text(encoding="utf-8")


def _parse(profile: str = WISE_PROFILE, *, filename: str = ""):  # type: ignore[no-untyped-def]
    return ImportService(_NoSession()).parse_queued_file(  # type: ignore[arg-type]
        _content(), profile, filename=filename
    )


class TestWiseQifDetection:
    def test_fixture_is_recognised_as_wise_qif(self) -> None:
        assert is_wise_qif_content(_content()) is True
        assert WiseQifPreprocessor.is_wise_qif(_content()) is True

    def test_wise_detector_covers_both_csv_and_qif(self) -> None:
        assert is_wise_content(_content()) is True

    def test_generic_upload_is_promoted_to_wise(self) -> None:
        assert detect_bank_profile(_content()) == WISE_PROFILE

    def test_plain_qif_without_wise_ids_is_not_claimed(self) -> None:
        """A Quicken-style QIF stays out of the Wise branch (explicitly out of scope)."""
        content = "!Type:Bank\nD01/15/2024\nT-10.00\nPCoffee\n^\n"
        assert is_wise_qif_content(content) is False
        assert detect_bank_profile(content) is None

    def test_wise_csv_is_not_mistaken_for_qif(self) -> None:
        csv_content = (FIXTURES / "jpy-travel-sample.csv").read_text(encoding="utf-8")
        assert is_wise_qif_content(csv_content) is False
        assert detect_bank_profile(csv_content) == WISE_PROFILE


class TestWiseQifRecords:
    def test_records_split_on_caret_and_skip_type_header(self) -> None:
        records = list(iter_qif_records(_content()))
        assert len(records) == 9
        first = records[0]
        assert first.date == "05/17/2026"
        assert first.amount == "-51571"
        assert first.payee == "Japanpost Bank(245950) GIFU"
        assert first.reference == "CARD-3802617048"
        assert first.memo == "Jan Kowalski 1234"

    def test_field_order_in_the_real_export_is_not_assumed(self) -> None:
        """Wise writes D, N, T, P, M — the parser keys off the letter, not position."""
        lines = [line[0] for line in _content().splitlines() if line and not line.startswith("!")]
        assert lines[:6] == ["D", "N", "T", "P", "M", "^"]

    def test_trailing_record_without_caret_is_kept(self) -> None:
        content = "!Type:Bank\nD05/17/2026\nT-1.00\nPX\nNCARD-1\n"
        assert len(list(iter_qif_records(content))) == 1


class TestWiseQifParsing:
    def test_fixture_parses_nine_rows_under_the_wise_profile(self) -> None:
        result = _parse()
        assert result.ok is True
        assert result.profile == WISE_PROFILE
        assert len(result.rows) == 9

    def test_generic_upload_parses_through_the_qif_branch(self) -> None:
        result = _parse(GENERIC_PROFILE)
        assert result.ok is True
        assert result.profile == WISE_PROFILE
        assert result.profile != MBANK_PROFILE
        assert result.needs_mapping is False
        assert len(result.rows) == 9

    def test_us_dates_are_parsed_as_month_first(self) -> None:
        rows = _parse().rows
        assert rows[0].date == datetime.date(2026, 5, 17)
        assert rows[-1].date == datetime.date(2026, 4, 17)

    def test_card_row_uses_payee_as_description(self) -> None:
        rows = _parse().rows
        card_row = next(r for r in rows if r.raw.get("reference") == "CARD-3802617048")
        assert card_row.amount == Decimal("-51571")
        assert card_row.description == "Japanpost Bank(245950) GIFU"

    def test_card_holder_memo_never_reaches_the_ledger(self) -> None:
        """``M`` is the holder name + last four, identical on every card row."""
        rows = _parse().rows
        assert {row.notes for row in rows} == {""}
        assert not any("Jan Kowalski" in row.description for row in rows)

    def test_top_up_is_income(self) -> None:
        rows = _parse().rows
        top_up = next(r for r in rows if r.raw.get("reference") == "TRANSFER-2134191896")
        assert top_up.amount == Decimal("100000")
        assert top_up.description == "Topped up account"

    def test_qif_descriptions_are_english_not_the_csv_polish(self) -> None:
        descriptions = {row.description for row in _parse().rows}
        assert "Topped up account" in descriptions
        assert "Doładowanie konta" not in descriptions

    def test_integer_amounts_of_the_real_export_parse_exactly(self) -> None:
        """Wise writes JPY with no decimal part at all (``T-51571``)."""
        amounts = {row.amount for row in _parse().rows}
        assert Decimal("-1811") in amounts
        assert Decimal("269000") in amounts

    def test_amount_with_thousands_separator_is_not_mangled(self) -> None:
        """`_parse_amount`'s auto mode would read this EU-style, as -1.811."""
        content = "!Type:Bank\nD05/17/2026\nT-1,811.00\nPBellmart NAGOYA\nNCARD-1\n^\n"
        rows = WiseQifPreprocessor.parse(content).rows
        assert rows[0].amount == Decimal("-1811.00")


class TestWiseQifMetadata:
    def test_the_body_names_no_currency_so_a_nameless_parse_has_none(self) -> None:
        """Wise puts the currency in the download name, never in the QIF body."""
        meta = WiseQifPreprocessor.extract_metadata(_content())
        assert meta.currency == ""
        assert meta.account_type == "Wise"
        assert "JPY" not in _content()

    def test_the_download_name_supplies_the_currency_the_body_lacks(self) -> None:
        meta = WiseQifPreprocessor.extract_metadata(_content(), filename=WISE_QIF_NAME)
        assert meta.currency == "JPY"

    def test_a_renamed_upload_leaves_the_currency_unknown(self) -> None:
        """Unknown, not wrong: a renamed file must stay importable."""
        meta = WiseQifPreprocessor.extract_metadata(_content(), filename="foo.qif")
        assert meta.currency == ""

    def test_period_spans_the_oldest_and_newest_record(self) -> None:
        meta = WiseQifPreprocessor.extract_metadata(_content())
        assert meta.date_from == datetime.date(2026, 4, 17)
        assert meta.date_to == datetime.date(2026, 5, 17)

    def test_the_records_outrank_the_names_wider_range(self) -> None:
        """The name holds the *requested* period; the rows hold the real one."""
        meta = WiseQifPreprocessor.extract_metadata(_content(), filename=WISE_QIF_NAME)
        assert meta.date_from == datetime.date(2026, 4, 17)
        assert meta.date_to == datetime.date(2026, 5, 17)

    def test_metadata_reaches_the_parse_result(self) -> None:
        result = _parse()
        assert result.metadata is not None
        assert result.metadata.date_to == datetime.date(2026, 5, 17)

    def test_the_upload_name_reaches_the_parse_result(self) -> None:
        result = _parse(filename=WISE_QIF_NAME)
        assert result.metadata is not None
        assert result.metadata.currency == "JPY"

    def test_a_generic_upload_promoted_to_wise_still_reads_its_name(self) -> None:
        result = _parse(GENERIC_PROFILE, filename=WISE_QIF_NAME)
        assert result.profile == WISE_PROFILE
        assert result.metadata is not None
        assert result.metadata.currency == "JPY"

    @staticmethod
    def _readiness(*, filename: str, account_currency: str) -> tuple[str | None, dict[str, object]]:
        from kaleta.services.import_service import (
            ImportReadinessCheck,
            validate_import_readiness,
        )

        return validate_import_readiness(
            ImportReadinessCheck(
                target_account_id=1,
                expense_cat_id=2,
                income_cat_id=3,
                profile=WISE_PROFILE,
                metadata=WiseQifPreprocessor.extract_metadata(_content(), filename=filename),
                account_currency=account_currency,
            )
        )

    def test_empty_currency_does_not_block_a_correct_import(self) -> None:
        """The mismatch guard must stay silent rather than reject on a guess."""
        error_key, _ = self._readiness(filename="", account_currency="JPY")
        assert error_key is None

    def test_a_renamed_upload_still_imports_onto_any_account(self) -> None:
        """Unknown must not block — a renamed file would otherwise be stuck."""
        error_key, _ = self._readiness(filename="foo.qif", account_currency="PLN")
        assert error_key is None

    def test_the_named_currency_blocks_the_wrong_account(self) -> None:
        """The whole point: a JPY statement must not land on a PLN account."""
        error_key, params = self._readiness(filename=WISE_QIF_NAME, account_currency="PLN")
        assert error_key == "import.currency_mismatch_block"
        assert params == {"file": "JPY", "account": "PLN"}

    def test_the_named_currency_lets_the_right_account_through(self) -> None:
        error_key, _ = self._readiness(filename=WISE_QIF_NAME, account_currency="JPY")
        assert error_key is None


class TestWiseQifFailureModes:
    def test_records_without_date_or_amount_are_skipped_not_errors(self) -> None:
        content = "!Type:Bank\nPOrphan payee\nNCARD-1\n^\nD05/17/2026\nT-1.00\nPX\nNCARD-2\n^\n"
        result = WiseQifPreprocessor.parse(content)
        assert result.skipped == 1
        assert result.errors == []
        assert len(result.rows) == 1

    def test_unparseable_amount_is_reported_per_record(self) -> None:
        content = "!Type:Bank\nD05/17/2026\nTnot-a-number\nPX\nNCARD-1\n^\n"
        result = WiseQifPreprocessor.parse(content)
        assert result.rows == []
        assert len(result.errors) == 1
        assert "QIF record 1" in result.errors[0]

    def test_empty_qif_fails_instead_of_falling_back_to_column_mapping(self) -> None:
        content = "!Type:Bank\nNCARD-placeholder\n^\n"
        result = ImportService(_NoSession()).parse_queued_file(content, WISE_PROFILE)  # type: ignore[arg-type]
        assert result.ok is False
        assert result.needs_mapping is False
        assert result.profile == WISE_PROFILE
        assert result.error_key == "import.qif_no_rows"


@pytest.mark.parametrize("profile", [WISE_PROFILE, GENERIC_PROFILE])
def test_wise_csv_path_is_untouched_by_the_qif_branch(profile: str) -> None:
    csv_content = (FIXTURES / "jpy-travel-sample.csv").read_text(encoding="utf-8")
    result = ImportService(_NoSession()).parse_queued_file(csv_content, profile)  # type: ignore[arg-type]
    assert result.ok is True
    assert result.profile == WISE_PROFILE
    assert len(result.rows) == 9
