"""Unit tests for ImportService — CSV parsing and internal transfer detection."""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest

from kaleta.services.import_service import ImportService, _parse_amount, _parse_date


# ── _parse_date helper ────────────────────────────────────────────────────────

class TestParseDate:

    @pytest.mark.parametrize("value,expected", [
        ("2024-01-15",  datetime.date(2024, 1, 15)),
        ("15.01.2024",  datetime.date(2024, 1, 15)),
        ("15/01/2024",  datetime.date(2024, 1, 15)),
        ("01/15/2024",  datetime.date(2024, 1, 15)),
        ("15-01-2024",  datetime.date(2024, 1, 15)),
        ("20240115",    datetime.date(2024, 1, 15)),
        ("  2024-01-15 ", datetime.date(2024, 1, 15)),  # whitespace trimmed
    ])
    def test_valid_date_formats(self, value: str, expected: datetime.date):
        assert _parse_date(value) == expected

    @pytest.mark.parametrize("value", [
        "not-a-date",
        "32.01.2024",
        "2024-13-01",
        "",
        "'; DROP TABLE transactions; --",
    ])
    def test_invalid_dates_raise(self, value: str):
        with pytest.raises(ValueError):
            _parse_date(value)


# ── _parse_amount helper ──────────────────────────────────────────────────────

class TestParseAmount:

    @pytest.mark.parametrize("value,expected", [
        ("100.00",    Decimal("100.00")),
        ("-245.50",   Decimal("-245.50")),
        ("1 234,56",  Decimal("1234.56")),   # PL format with space separator
        ("1.234,56",  Decimal("1234.56")),   # EU format
        ("1234,56",   Decimal("1234.56")),   # comma decimal
        ("100 PLN",   Decimal("100")),        # with currency suffix
        (" 99.99 ",   Decimal("99.99")),      # whitespace
    ])
    def test_valid_amounts(self, value: str, expected: Decimal):
        assert _parse_amount(value) == expected

    @pytest.mark.parametrize("value", [
        "not_a_number",
        "",
        "free",
        "'; DROP TABLE--",
    ])
    def test_invalid_amounts_raise(self, value: str):
        with pytest.raises(ValueError):
            _parse_amount(value)


# ── ImportService.parse_csv ───────────────────────────────────────────────────

def _svc() -> ImportService:
    """ImportService without a DB session — parse_csv is pure (no DB needed)."""
    return ImportService.__new__(ImportService)


class TestParseCsv:

    def test_basic_semicolon_csv(self):
        csv = "data;kwota;opis\n2024-01-15;-100.00;Biedronka\n2024-01-16;5000.00;Pensja\n"
        result = _svc().parse_csv(csv)
        assert len(result.rows) == 2
        assert result.errors == []
        assert result.rows[0].amount == Decimal("-100.00")
        assert result.rows[1].amount == Decimal("5000.00")

    def test_basic_comma_csv(self):
        csv = "date,amount,description\n2024-01-15,-50.00,Coffee\n"
        result = _svc().parse_csv(csv)
        assert len(result.rows) == 1
        assert result.rows[0].description == "Coffee"

    def test_tab_delimiter(self):
        csv = "date\tamount\tdescription\n2024-01-15\t-50.00\tTest\n"
        result = _svc().parse_csv(csv, delimiter="\t")
        assert len(result.rows) == 1

    def test_debit_credit_columns(self):
        csv = "Date,Debit,Credit,Description\n2024-01-15,200.00,,Expense\n2024-01-16,,5000.00,Income\n"
        result = _svc().parse_csv(csv)
        assert len(result.rows) == 2
        assert result.rows[0].amount == Decimal("-200.00")
        assert result.rows[1].amount == Decimal("5000.00")

    def test_polish_date_format(self):
        csv = "data;kwota;opis\n15.03.2024;-99.99;Test\n"
        result = _svc().parse_csv(csv)
        assert result.rows[0].date == datetime.date(2024, 3, 15)

    def test_missing_date_column_returns_error(self):
        csv = "amount,description\n100.00,Test\n"
        result = _svc().parse_csv(csv)
        assert any("date" in e.lower() for e in result.errors)
        assert len(result.rows) == 0

    def test_missing_amount_column_returns_error(self):
        csv = "date,description\n2024-01-15,Test\n"
        result = _svc().parse_csv(csv)
        assert len(result.errors) > 0
        assert len(result.rows) == 0

    def test_empty_csv_returns_error(self):
        result = _svc().parse_csv("")
        assert len(result.errors) > 0

    def test_invalid_amount_rows_reported_as_errors(self):
        csv = "date,amount,description\n2024-01-15,NOT_A_NUMBER,Bad\n2024-01-16,-50.00,Good\n"
        result = _svc().parse_csv(csv)
        assert len(result.rows) == 1       # only the good row
        assert len(result.errors) == 1     # one error reported

    def test_empty_amount_rows_skipped(self):
        csv = "date,amount,description\n2024-01-15,,Skipped\n2024-01-16,-50.00,Good\n"
        result = _svc().parse_csv(csv)
        assert len(result.rows) == 1
        assert result.skipped == 1

    # ── Security ──────────────────────────────────────────────────────────

    def test_sql_injection_in_description_column(self):
        """SQL injection in CSV description is parsed as plain text."""
        payload = "'; DROP TABLE transactions; --"
        csv = f"date,amount,description\n2024-01-15,-50.00,{payload}\n"
        result = _svc().parse_csv(csv)
        assert len(result.rows) == 1
        assert result.rows[0].description == payload

    def test_xss_in_description_column(self):
        payload = "<script>alert('xss')</script>"
        csv = f"date,amount,description\n2024-01-15,-50.00,{payload}\n"
        result = _svc().parse_csv(csv)
        assert result.rows[0].description == payload

    def test_csv_formula_injection_stored_as_plain_text(self):
        """Spreadsheet formula injection (=CMD, @SUM) must be stored verbatim."""
        for formula in ["=CMD('calc.exe')", "@SUM(1+1)*cmd|' /C calc'!A0", "=HYPERLINK('evil.com')"]:
            csv = f"date,amount,description\n2024-01-15,-1.00,{formula}\n"
            result = _svc().parse_csv(csv)
            assert len(result.rows) == 1
            assert result.rows[0].description == formula

    def test_sql_injection_in_amount_column_raises_parse_error(self):
        """A SQL injection string in the amount column cannot be a valid number."""
        csv = "date,amount,description\n2024-01-15,'; DROP TABLE;--,Test\n"
        result = _svc().parse_csv(csv)
        assert len(result.rows) == 0
        assert len(result.errors) == 1

    def test_null_byte_in_description(self):
        """Null bytes in description are kept as-is (no execution risk in ORM)."""
        payload = "normal\x00evil"
        csv = f"date,amount,description\n2024-01-15,-1.00,{payload}\n"
        result = _svc().parse_csv(csv)
        assert result.rows[0].description == payload

    def test_very_large_csv_does_not_error(self):
        """1000-row CSV parses without exceptions."""
        rows = "\n".join(f"2024-01-{(i % 28) + 1:02d},-{i}.00,Item {i}" for i in range(1, 1001))
        csv = f"date,amount,description\n{rows}\n"
        result = _svc().parse_csv(csv)
        assert len(result.rows) == 1000
        assert result.errors == []
