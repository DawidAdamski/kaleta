# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parse the Wise MT940 statement export shape from the dogfood fixture.

``jpy-travel-sample.mt940`` holds the same nine movements as the CSV and QIF
fixtures beside it, in the SWIFT layout the maintainer's real Wise MT940 uses
(see ``tests/e2e/fixtures/import/wise/NOTES.md`` for exactly which parts of
that file are reproduced and which are reconstructed). Expected values here
are literals read off the MT940 fixture itself — MT940 says different things
than the other two exports, so nothing may be borrowed across them or
computed by the parser under test.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from kaleta.exceptions import ImportError_
from kaleta.services.import_profiles import (
    GENERIC_PROFILE,
    MBANK_PROFILE,
    WISE_PROFILE,
    detect_bank_profile,
    is_wise_content,
    is_wise_mt940_content,
    is_wise_qif_content,
)
from kaleta.services.import_service import (
    ImportService,
    WiseMt940Preprocessor,
    iter_mt940_entries,
    iter_mt940_fields,
    parse_mt940_balance,
    parse_mt940_statement_line,
)

FIXTURES = Path(__file__).resolve().parents[2] / "e2e" / "fixtures" / "import" / "wise"
MT940_FIXTURE = FIXTURES / "jpy-travel-sample.mt940"

# The shape Wise gives every statement download. MT940 needs no name read —
# it states its own currency — so this exists only to prove that.
WISE_MT940_NAME = "statement_12345678_JPY_2026-04-01_2026-06-30.mt940"


class _NoSession:
    session = None


def _content() -> str:
    return MT940_FIXTURE.read_text(encoding="utf-8")


def _parse(profile: str = WISE_PROFILE, *, filename: str = ""):  # type: ignore[no-untyped-def]
    return ImportService(_NoSession()).parse_queued_file(  # type: ignore[arg-type]
        _content(), profile, filename=filename
    )


class TestWiseMt940Detection:
    def test_fixture_is_recognised_as_wise_mt940(self) -> None:
        assert is_wise_mt940_content(_content()) is True
        assert WiseMt940Preprocessor.is_wise_mt940(_content()) is True

    def test_wise_detector_covers_csv_qif_and_mt940(self) -> None:
        assert is_wise_content(_content()) is True

    def test_generic_upload_is_promoted_to_wise(self) -> None:
        assert detect_bank_profile(_content()) == WISE_PROFILE

    def test_another_banks_mt940_is_not_claimed(self) -> None:
        """Generic MT940 is out of scope — only Wise's own bank code claims a file."""
        content = ":25:PL61109010140000071219812874\n:61:260517D51571,FMSCNONREF\n"
        assert is_wise_mt940_content(content) is False
        assert detect_bank_profile(content) is None

    def test_the_bank_code_alone_is_not_enough_without_statement_lines(self) -> None:
        """A file naming Wise but holding no ``:61:`` entry is not a statement."""
        content = ":20:WISE-STATEMENT\n:25:GB33TRWI23145600000123\n"
        assert is_wise_mt940_content(content) is False

    def test_the_wise_bic_claims_a_file_whose_account_tag_does_not(self) -> None:
        """A Wise MT940 may name the bank as a BIC rather than inside the IBAN."""
        content = ":20:REF\n:25:PL61109010140000071219812874\n:61:260517D1,FMSCNONREF\nTRWIGB2L\n"
        assert is_wise_mt940_content(content) is True

    def test_an_iban_is_not_mistaken_for_a_bic(self) -> None:
        """``TRWI2314`` inside an IBAN has digits where a BIC needs letters."""
        content = ":25:GB33TRWI23145600000123\n"
        assert is_wise_mt940_content(content) is False

    def test_wise_qif_and_csv_are_not_mistaken_for_mt940(self) -> None:
        for name in ("jpy-travel-sample.qif", "jpy-travel-sample.csv"):
            other = (FIXTURES / name).read_text(encoding="utf-8")
            assert is_wise_mt940_content(other) is False
        assert is_wise_qif_content(_content()) is False


class TestMt940FieldTokenizer:
    def test_fields_carry_their_continuation_lines(self) -> None:
        fields = list(iter_mt940_fields(_content()))
        tags = [tag for tag, _ in fields]
        assert tags[:5] == ["20", "25", "28C", "60F", "61"]
        assert tags[-1] == "62F"
        first_entry = next(lines for tag, lines in fields if tag == "61")
        assert first_entry == ["260417C269000,FTRFNONREF", "TRANSFER-2081544402"]

    def test_lines_before_the_first_tag_belong_to_no_field(self) -> None:
        """A SWIFT envelope block ahead of the statement is not a continuation."""
        fields = list(iter_mt940_fields("{1:F01TRWIGB2LXXXX}\n:20:REF\n"))
        assert fields == [("20", ["REF"])]

    def test_entries_are_one_per_statement_line(self) -> None:
        entries = list(iter_mt940_entries(_content()))
        assert len(entries) == 9
        assert entries[0].statement_line == "260417C269000,FTRFNONREF"
        assert entries[0].details == "TRANSFER-2081544402"
        assert entries[0].narrative == "/EXCH/44,2099/"

    def test_a_card_entry_has_no_narrative(self) -> None:
        """Wise writes ``:86:`` on top-ups only — cards carry the id and nothing else."""
        entries = list(iter_mt940_entries(_content()))
        card = next(e for e in entries if e.details == "CARD-3802617048")
        assert card.narrative == ""

    def test_the_closing_balance_closes_the_last_entry(self) -> None:
        content = ":61:260517D1,FMSCNONREF\nCARD-1\n:62F:C260517JPY0,\n"
        entries = list(iter_mt940_entries(content))
        assert len(entries) == 1
        assert entries[0].details == "CARD-1"

    def test_a_narrative_after_the_closing_balance_attaches_to_nothing(self) -> None:
        content = ":61:260517D1,FMSCNONREF\nCARD-1\n:62F:C260517JPY0,\n:86:statement footer\n"
        entries = list(iter_mt940_entries(content))
        assert len(entries) == 1
        assert entries[0].narrative == ""


class TestMt940StatementLine:
    def test_the_maintainers_sample_line_parses_field_by_field(self) -> None:
        line = parse_mt940_statement_line("260517D51571,FMSCNONREF")
        assert line.value_date == datetime.date(2026, 5, 17)
        assert line.amount == Decimal("-51571")
        assert line.type_code == "FMSC"
        assert line.reference == "NONREF"

    def test_a_credit_keeps_its_positive_sign(self) -> None:
        assert parse_mt940_statement_line("260417C269000,FTRFNONREF").amount == Decimal("269000")

    def test_an_entry_date_after_the_value_date_is_skipped(self) -> None:
        """SWIFT allows ``YYMMDD`` + ``MMDD``; the value date is the booking date."""
        line = parse_mt940_statement_line("2605170518D51571,FMSCNONREF")
        assert line.value_date == datetime.date(2026, 5, 17)
        assert line.amount == Decimal("-51571")

    def test_a_funds_code_between_the_mark_and_the_amount_is_skipped(self) -> None:
        line = parse_mt940_statement_line("260517DR51571,FMSCNONREF")
        assert line.amount == Decimal("-51571")

    def test_the_comma_is_the_decimal_separator_not_a_thousands_mark(self) -> None:
        """SWIFT writes 1811.50 as ``1811,50`` — reading it as 181150 would be silent."""
        assert parse_mt940_statement_line("260517D1811,50NTRFNONREF").amount == Decimal("-1811.50")

    def test_a_bank_reference_after_the_customer_one_is_not_part_of_it(self) -> None:
        line = parse_mt940_statement_line("260517D1,FMSCCUSTOMERREF//BANKREF")
        assert line.reference == "CUSTOMERREF"

    def test_type_codes_other_than_the_fixtures_are_read_the_same_way(self) -> None:
        """The parser keys off the line's structure, not the four-letter code."""
        for code in ("NTRF", "NMSC", "S103"):
            assert parse_mt940_statement_line(f"260517D1,{code}NONREF").type_code == code

    @pytest.mark.parametrize(
        "line",
        [
            "260517X51571,FMSCNONREF",
            "260517RC51571,FMSCNONREF",
            "not a statement line",
            "",
        ],
    )
    def test_a_line_that_is_not_a_statement_line_raises(self, line: str) -> None:
        """Including reversals: no fixture proves their sign, so they must not be guessed."""
        with pytest.raises(ImportError_):
            parse_mt940_statement_line(line)


class TestMt940Balance:
    def test_the_opening_balance_of_the_fixture(self) -> None:
        balance = parse_mt940_balance("C260417JPY0,")
        assert balance is not None
        assert balance.currency == "JPY"
        assert balance.amount == Decimal("0")

    def test_a_debit_balance_is_negative(self) -> None:
        balance = parse_mt940_balance("D260517EUR1234,56")
        assert balance is not None
        assert balance.amount == Decimal("-1234.56")

    def test_a_field_that_is_not_a_balance_yields_none(self) -> None:
        assert parse_mt940_balance("260517D51571,FMSCNONREF") is None


class TestWiseMt940Parsing:
    def test_fixture_parses_nine_rows_under_the_wise_profile(self) -> None:
        result = _parse()
        assert result.ok is True
        assert result.profile == WISE_PROFILE
        assert len(result.rows) == 9
        assert result.errors == []

    def test_generic_upload_parses_through_the_mt940_branch(self) -> None:
        result = _parse(GENERIC_PROFILE)
        assert result.ok is True
        assert result.profile == WISE_PROFILE
        assert result.profile != MBANK_PROFILE
        assert result.needs_mapping is False
        assert len(result.rows) == 9

    def test_two_digit_years_resolve_into_this_century(self) -> None:
        rows = _parse().rows
        assert rows[0].date == datetime.date(2026, 4, 17)
        assert rows[-1].date == datetime.date(2026, 5, 17)

    def test_debits_are_expenses_and_credits_income(self) -> None:
        rows = _parse().rows
        card = next(r for r in rows if r.raw.get("reference") == "CARD-3802617048")
        top_up = next(r for r in rows if r.raw.get("reference") == "TRANSFER-2134191896")
        assert card.amount == Decimal("-51571")
        assert top_up.amount == Decimal("100000")

    def test_the_transaction_id_is_the_description(self) -> None:
        """MT940 names no merchant at all — the Wise id is all there is."""
        rows = _parse().rows
        assert rows[0].description == "TRANSFER-2081544402"
        assert {r.description for r in rows if r.description.startswith("CARD-")} == {
            "CARD-3773297563",
            "CARD-3773579244",
            "CARD-3773586456",
            "CARD-3773587991",
            "CARD-3790648970",
            "CARD-3802350449",
            "CARD-3802617048",
        }

    def test_the_merchant_names_of_the_csv_are_nowhere_in_this_format(self) -> None:
        assert "Japanpost" not in _content()
        assert not any("Japanpost" in row.description for row in _parse().rows)

    def test_the_exchange_rate_is_kept_beside_the_row_not_as_its_name(self) -> None:
        """``/EXCH/43,5034/`` says what a rate was, never what was bought."""
        top_up = next(r for r in _parse().rows if r.raw.get("reference") == "TRANSFER-2134191896")
        assert top_up.raw["narrative"] == "/EXCH/43,5034/"
        assert "EXCH" not in top_up.description

    def test_nothing_is_persisted_as_notes(self) -> None:
        assert {row.notes for row in _parse().rows} == {""}

    def test_entry_order_in_the_file_is_not_assumed(self) -> None:
        """Each entry dates itself, so a newest-first statement parses the same.

        The fixture runs oldest-first, the order MT940's opening and closing
        balances imply; nothing in the parser depends on that.
        """
        lines = _content().splitlines()
        first_entry = lines.index(":61:260417C269000,FTRFNONREF")
        head, body, tail = lines[:first_entry], lines[first_entry:-1], lines[-1:]
        reversed_content = "\n".join([*head, *_reverse_entries(body), *tail])

        rows = WiseMt940Preprocessor.parse(reversed_content).rows
        assert len(rows) == 9
        assert [row.date for row in rows] == [row.date for row in reversed(_parse().rows)]
        assert rows[0].description == "CARD-3802617048"

    def test_the_customer_reference_names_a_row_that_has_no_detail_line(self) -> None:
        content = ":25:GB33TRWI23145600000123\n:61:260517D1811,FMSCINVOICE-42\n"
        rows = WiseMt940Preprocessor.parse(content).rows
        assert rows[0].description == "INVOICE-42"

    def test_nonref_is_swift_for_no_reference_and_never_becomes_a_description(self) -> None:
        content = ":25:GB33TRWI23145600000123\n:61:260517D1811,FMSCNONREF\n"
        rows = WiseMt940Preprocessor.parse(content).rows
        assert rows[0].description == ""


def _reverse_entries(body: list[str]) -> list[str]:
    """Regroup ``:61:``-led blocks and reverse their order, keeping each intact."""
    blocks: list[list[str]] = []
    for line in body:
        if line.startswith(":61:") or not blocks:
            blocks.append([line])
        else:
            blocks[-1].append(line)
    return [line for block in reversed(blocks) for line in block]


class TestWiseMt940Metadata:
    def test_the_file_states_its_own_currency(self) -> None:
        """The QIF had none in its body; MT940 puts it in the balance fields."""
        meta = WiseMt940Preprocessor.extract_metadata(_content())
        assert meta.currency == "JPY"
        assert meta.account_type == "Wise"

    def test_no_download_name_is_needed_for_the_currency(self) -> None:
        result = _parse(filename="")
        assert result.metadata is not None
        assert result.metadata.currency == "JPY"

    def test_a_renamed_upload_still_states_its_currency(self) -> None:
        """The whole difference from the QIF path: renaming loses nothing."""
        renamed = _parse(filename="foo.mt940")
        named = _parse(filename=WISE_MT940_NAME)
        assert renamed.metadata is not None
        assert named.metadata is not None
        assert renamed.metadata.currency == named.metadata.currency == "JPY"

    def test_the_closing_balance_supplies_a_currency_no_opening_one_does(self) -> None:
        content = ":25:GB33TRWI23145600000123\n:61:260517D1,FMSCNONREF\n:62F:C260517JPY0,\n"
        assert WiseMt940Preprocessor.extract_metadata(content).currency == "JPY"

    def test_the_account_tag_becomes_the_banner_account(self) -> None:
        meta = WiseMt940Preprocessor.extract_metadata(_content())
        assert meta.account_number == "GB33TRWI23145600000123"
        assert meta.account_number_digits == "3323145600000123"

    def test_a_currency_suffixed_account_tag_keeps_only_the_account(self) -> None:
        content = ":25:GB33TRWI23145600000123/JPY\n:61:260517D1,FMSCNONREF\n"
        meta = WiseMt940Preprocessor.extract_metadata(content)
        assert meta.account_number == "GB33TRWI23145600000123"

    def test_the_period_spans_the_oldest_and_newest_entry(self) -> None:
        meta = WiseMt940Preprocessor.extract_metadata(_content())
        assert meta.date_from == datetime.date(2026, 4, 17)
        assert meta.date_to == datetime.date(2026, 5, 17)

    def test_the_entries_outrank_the_periods_the_header_asks_for(self) -> None:
        """The download name asks for 04-01 – 06-30; the movements run 04-17 – 05-17."""
        result = _parse(filename=WISE_MT940_NAME)
        assert result.metadata is not None
        assert result.metadata.date_from == datetime.date(2026, 4, 17)
        assert result.metadata.date_to == datetime.date(2026, 5, 17)

    @staticmethod
    def _readiness(*, account_currency: str) -> tuple[str | None, dict[str, object]]:
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
                metadata=WiseMt940Preprocessor.extract_metadata(_content()),
                account_currency=account_currency,
            )
        )

    def test_the_stated_currency_blocks_the_wrong_account(self) -> None:
        error_key, params = self._readiness(account_currency="PLN")
        assert error_key == "import.currency_mismatch_block"
        assert params == {"file": "JPY", "account": "PLN"}

    def test_the_stated_currency_lets_the_right_account_through(self) -> None:
        error_key, _ = self._readiness(account_currency="JPY")
        assert error_key is None


class TestWiseMt940FailureModes:
    def test_an_unparseable_entry_is_reported_and_the_rest_still_import(self) -> None:
        content = (
            ":25:GB33TRWI23145600000123\n"
            ":61:260517X51571,FMSCNONREF\n"
            "CARD-1\n"
            ":61:260517D1811,FMSCNONREF\n"
            "CARD-2\n"
        )
        result = WiseMt940Preprocessor.parse(content)
        assert len(result.rows) == 1
        assert len(result.errors) == 1
        assert "MT940 entry 1" in result.errors[0]

    def test_an_mt940_without_entries_fails_instead_of_asking_for_a_mapping(self) -> None:
        content = ":20:WISE-STATEMENT\n:25:GB33TRWI23145600000123\n:61:not-a-line\n"
        result = ImportService(_NoSession()).parse_queued_file(content, WISE_PROFILE)  # type: ignore[arg-type]
        assert result.ok is False
        assert result.needs_mapping is False
        assert result.profile == WISE_PROFILE
        assert result.error_key == "import.mt940_no_rows"


@pytest.mark.parametrize("fixture_name", ["jpy-travel-sample.csv", "jpy-travel-sample.qif"])
@pytest.mark.parametrize("profile", [WISE_PROFILE, GENERIC_PROFILE])
def test_the_other_wise_paths_are_untouched_by_the_mt940_branch(
    fixture_name: str, profile: str
) -> None:
    content = (FIXTURES / fixture_name).read_text(encoding="utf-8")
    result = ImportService(_NoSession()).parse_queued_file(content, profile)  # type: ignore[arg-type]
    assert result.ok is True
    assert result.profile == WISE_PROFILE
    assert len(result.rows) == 9
