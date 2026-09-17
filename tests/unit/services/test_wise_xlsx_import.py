# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parse the Wise XLSX statement export from the anonymized dogfood fixture.

``jpy-travel-sample.xlsx`` is the maintainer's real Wise workbook with only the
card-holder name and card last four replaced; every other part of the archive
is the bank's own bytes. Expected values here are literals read off that
workbook.

The XLSX and the CSV describe the same nine movements but not identically —
different column names, a different column order, English descriptions against
the CSV's Polish — so nothing may be borrowed across the two.
"""

from __future__ import annotations

import datetime
import io
import zipfile
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest

from kaleta.services.import_profiles import (
    GENERIC_PROFILE,
    WISE_PROFILE,
    detect_bank_profile,
)
from kaleta.services.import_service import (
    ImportService,
    WiseXlsxPreprocessor,
    is_wise_xlsx_bytes,
)

FIXTURES = Path(__file__).resolve().parents[2] / "e2e" / "fixtures" / "import" / "wise"
XLSX_FIXTURE = FIXTURES / "jpy-travel-sample.xlsx"

WISE_XLSX_NAME = "statement_12345678_JPY_2026-04-01_2026-06-30.xlsx"


class _NoSession:
    session = None


def _raw() -> bytes:
    return XLSX_FIXTURE.read_bytes()


def _parse(profile: str = WISE_PROFILE, *, filename: str = ""):  # type: ignore[no-untyped-def]
    return ImportService(_NoSession()).parse_queued_file(  # type: ignore[arg-type]
        "", profile, filename=filename, raw=_raw()
    )


class TestWiseXlsxDetection:
    def test_fixture_is_recognised_as_wise_xlsx(self) -> None:
        assert is_wise_xlsx_bytes(_raw()) is True
        assert WiseXlsxPreprocessor.is_wise_xlsx(_raw()) is True

    def test_a_generic_upload_reaches_the_xlsx_branch_on_its_bytes(self) -> None:
        """The decoded text of a workbook is noise, so the bytes decide."""
        result = _parse(GENERIC_PROFILE)
        assert result.ok is True
        assert result.profile == WISE_PROFILE

    def test_the_csv_detector_would_not_have_found_it(self) -> None:
        """Wise names the first XLSX column ``ID``, not ``TransferWise ID``."""
        with zipfile.ZipFile(io.BytesIO(_raw())) as archive:
            shared = archive.read("xl/sharedStrings.xml").decode("utf-8")
        assert "TransferWise ID" not in shared
        assert ">ID</t>" in shared

    def test_text_uploads_are_not_claimed_by_the_xlsx_branch(self) -> None:
        for name in ("jpy-travel-sample.csv", "jpy-travel-sample.qif"):
            assert is_wise_xlsx_bytes((FIXTURES / name).read_bytes()) is False

    def test_bytes_that_are_not_a_zip_are_rejected_before_unpacking(self) -> None:
        assert is_wise_xlsx_bytes(b"date,amount\n2026-01-01,-1\n") is False
        assert is_wise_xlsx_bytes(b"") is False

    def test_a_truncated_zip_is_rejected_rather_than_raising(self) -> None:
        assert is_wise_xlsx_bytes(_raw()[:200]) is False

    def test_a_header_inlined_instead_of_shared_is_still_found(self) -> None:
        """openpyxl writes no string table for a small book — it inlines them."""
        openpyxl = pytest.importorskip("openpyxl")
        workbook = openpyxl.Workbook()
        workbook.active.append(
            ["ID", "Running Balance", "Exchange To Amount", "Transaction Details Type"]
        )
        buffer = io.BytesIO()
        workbook.save(buffer)
        with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as archive:
            assert "xl/sharedStrings.xml" not in archive.namelist()
        assert is_wise_xlsx_bytes(buffer.getvalue()) is True

    def test_another_tools_workbook_is_not_claimed(self) -> None:
        """A valid xlsx without Wise's own columns falls through unclaimed."""
        openpyxl = pytest.importorskip("openpyxl")
        workbook = openpyxl.Workbook()
        workbook.active.append(["Date", "Amount", "Description"])
        workbook.active.append([datetime.date(2026, 1, 1), -10, "Coffee"])
        buffer = io.BytesIO()
        workbook.save(buffer)
        assert is_wise_xlsx_bytes(buffer.getvalue()) is False

    def test_the_text_profile_detector_is_untouched(self) -> None:
        """``detect_bank_profile`` reads text; the workbook never reaches it."""
        assert detect_bank_profile("") is None


class TestWiseXlsxParsing:
    def test_fixture_parses_nine_rows_under_the_wise_profile(self) -> None:
        result = _parse()
        assert result.ok is True
        assert result.profile == WISE_PROFILE
        assert result.needs_mapping is False
        assert len(result.rows) == 9
        assert result.errors == []

    def test_the_sheet_runs_newest_first(self) -> None:
        rows = _parse().rows
        assert rows[0].date == datetime.date(2026, 5, 17)
        assert rows[-1].date == datetime.date(2026, 4, 17)

    def test_excel_serial_dates_resolve_to_real_days(self) -> None:
        """The workbook stores ``46159``, not a date string."""
        with zipfile.ZipFile(io.BytesIO(_raw())) as archive:
            sheet = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
        assert "46159" in sheet
        assert "2026-05-17" not in sheet
        assert _parse().rows[0].date == datetime.date(2026, 5, 17)

    def test_debits_are_expenses_and_credits_income(self) -> None:
        rows = _parse().rows
        assert rows[0].amount == Decimal("-51571")
        assert rows[-1].amount == Decimal("269000")

    def test_the_merchant_wins_over_the_english_description(self) -> None:
        """Same rule as the CSV path: the ledger gets the merchant, not the prose."""
        row = _parse().rows[0]
        assert row.description == "Japanpost Bank(245950) GIFU"
        assert row.raw["Description"].startswith("Card transaction of 50,220 JPY")

    def test_descriptions_are_english_not_the_csv_polish(self) -> None:
        descriptions = {row.description for row in _parse().rows}
        assert "Topped up account" in descriptions
        assert "Doładowanie konta" not in descriptions

    def test_a_top_up_falls_back_to_the_description_having_no_merchant(self) -> None:
        top_up = next(r for r in _parse().rows if r.raw["ID"] == "TRANSFER-2134191896")
        assert top_up.description == "Topped up account"
        assert top_up.amount == Decimal("100000")

    def test_the_card_holder_never_becomes_a_description(self) -> None:
        assert not any("Jan Kowalski" in row.description for row in _parse().rows)

    def test_nothing_is_persisted_as_notes(self) -> None:
        assert {row.notes for row in _parse().rows} == {""}

    def test_columns_are_matched_by_name_not_position(self) -> None:
        """The XLSX column order is not the CSV's — position would mis-map.

        ``Total Fees`` sits at index 11 in the workbook where the CSV has
        ``Payer Name``, so a positional reader would put a fee where a name
        belongs.
        """
        openpyxl = pytest.importorskip("openpyxl")
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            workbook = openpyxl.load_workbook(io.BytesIO(_raw()))
        headers = [cell.value for cell in workbook.worksheets[0][1]]
        assert headers[0] == "ID"
        assert headers[11] == "Total Fees"

        csv_headers = (
            (FIXTURES / "jpy-travel-sample.csv")
            .read_text(encoding="utf-8")
            .splitlines()[0]
            .replace('"', "")
            .split(",")
        )
        assert csv_headers[0] == "TransferWise ID"
        assert csv_headers[11] == "Payer Name"

    def test_the_bogus_sheet_dimension_does_not_hide_the_rows(self) -> None:
        """Wise declares ``<dimension ref="A1"/>`` — a read-only load sees one cell."""
        with zipfile.ZipFile(io.BytesIO(_raw())) as archive:
            sheet = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
        assert '<dimension ref="A1"/>' in sheet
        assert len(_parse().rows) == 9


class TestWiseXlsxMetadata:
    def test_the_currency_column_states_the_currency(self) -> None:
        meta = WiseXlsxPreprocessor.extract_metadata(_raw())
        assert meta.currency == "JPY"
        assert meta.account_type == "Wise"

    def test_no_download_name_is_needed(self) -> None:
        """Unlike the QIF, a renamed workbook still knows its own currency."""
        renamed = _parse(filename="foo.xlsx")
        named = _parse(filename=WISE_XLSX_NAME)
        assert renamed.metadata is not None
        assert named.metadata is not None
        assert renamed.metadata.currency == named.metadata.currency == "JPY"

    def test_the_period_spans_the_oldest_and_newest_row(self) -> None:
        meta = WiseXlsxPreprocessor.extract_metadata(_raw())
        assert meta.date_from == datetime.date(2026, 4, 17)
        assert meta.date_to == datetime.date(2026, 5, 17)

    def test_the_holder_column_fills_the_banner_client_name(self) -> None:
        assert WiseXlsxPreprocessor.extract_metadata(_raw()).client_name == "Jan Kowalski"

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
                metadata=WiseXlsxPreprocessor.extract_metadata(_raw()),
                account_currency=account_currency,
            )
        )

    def test_the_stated_currency_blocks_the_wrong_account(self) -> None:
        error_key, params = self._readiness(account_currency="PLN")
        assert error_key == "import.currency_mismatch_block"
        assert params == {"file": "JPY", "account": "PLN"}

    def test_the_stated_currency_lets_the_right_account_through(self) -> None:
        assert self._readiness(account_currency="JPY")[0] is None


class TestWiseXlsxFailureModes:
    def test_a_workbook_with_only_headers_fails_without_asking_for_a_mapping(self) -> None:
        openpyxl = pytest.importorskip("openpyxl")
        workbook = openpyxl.Workbook()
        workbook.active.append(
            [
                "ID",
                "Date",
                "Amount",
                "Running Balance",
                "Exchange To Amount",
                "Transaction Details Type",
            ]
        )
        buffer = io.BytesIO()
        workbook.save(buffer)

        result = ImportService(_NoSession()).parse_queued_file(  # type: ignore[arg-type]
            "", WISE_PROFILE, raw=buffer.getvalue()
        )
        assert result.ok is False
        assert result.needs_mapping is False
        assert result.error_key == "import.xlsx_no_rows"

    def test_a_row_without_a_date_is_skipped_not_an_error(self) -> None:
        openpyxl = pytest.importorskip("openpyxl")
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.append(["ID", "Date", "Amount", "Currency", "Description"])
        sheet.append(["CARD-1", None, -10, "JPY", "No date"])
        sheet.append(["CARD-2", datetime.date(2026, 5, 17), -20, "JPY", "Fine"])
        buffer = io.BytesIO()
        workbook.save(buffer)

        result = WiseXlsxPreprocessor.parse(buffer.getvalue())
        assert result.skipped == 1
        assert result.errors == []
        assert len(result.rows) == 1

    def test_a_missing_extra_is_reported_instead_of_raising(self) -> None:
        """A base install has no openpyxl; the upload must say so, not traceback."""
        with patch.object(WiseXlsxPreprocessor, "is_available", return_value=False):
            result = ImportService(_NoSession()).parse_queued_file(  # type: ignore[arg-type]
                "", WISE_PROFILE, raw=_raw()
            )
        assert result.ok is False
        assert result.error_key == "import.xlsx_extra_missing"


@pytest.mark.parametrize(
    "fixture_name", ["jpy-travel-sample.csv", "jpy-travel-sample.qif", "jpy-travel-sample.mt940"]
)
@pytest.mark.parametrize("profile", [WISE_PROFILE, GENERIC_PROFILE])
def test_the_other_wise_paths_are_untouched_by_the_xlsx_branch(
    fixture_name: str, profile: str
) -> None:
    path = FIXTURES / fixture_name
    result = ImportService(_NoSession()).parse_queued_file(  # type: ignore[arg-type]
        path.read_text(encoding="utf-8"), profile, raw=path.read_bytes()
    )
    assert result.ok is True
    assert result.profile == WISE_PROFILE
    assert len(result.rows) == 9
