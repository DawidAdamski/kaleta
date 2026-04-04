"""Unit tests for ImportService — CSV parsing and internal transfer detection."""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.account import AccountType
from kaleta.models.category import CategoryType
from kaleta.models.transaction import TransactionType
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.category import CategoryCreate
from kaleta.services import AccountService, CategoryService
from kaleta.services.import_service import ImportService, ParsedRow, _parse_amount, _parse_date

# ── _parse_date helper ────────────────────────────────────────────────────────


class TestParseDate:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("2024-01-15", datetime.date(2024, 1, 15)),
            ("15.01.2024", datetime.date(2024, 1, 15)),
            ("15/01/2024", datetime.date(2024, 1, 15)),
            ("01/15/2024", datetime.date(2024, 1, 15)),
            ("15-01-2024", datetime.date(2024, 1, 15)),
            ("20240115", datetime.date(2024, 1, 15)),
            ("  2024-01-15 ", datetime.date(2024, 1, 15)),  # whitespace trimmed
        ],
    )
    def test_valid_date_formats(self, value: str, expected: datetime.date):
        assert _parse_date(value) == expected

    @pytest.mark.parametrize(
        "value",
        [
            "not-a-date",
            "32.01.2024",
            "2024-13-01",
            "",
            "'; DROP TABLE transactions; --",
        ],
    )
    def test_invalid_dates_raise(self, value: str):
        with pytest.raises(ValueError):
            _parse_date(value)


# ── _parse_amount helper ──────────────────────────────────────────────────────


class TestParseAmount:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("100.00", Decimal("100.00")),
            ("-245.50", Decimal("-245.50")),
            ("1 234,56", Decimal("1234.56")),  # PL format with space separator
            ("1.234,56", Decimal("1234.56")),  # EU format
            ("1234,56", Decimal("1234.56")),  # comma decimal
            ("100 PLN", Decimal("100")),  # with currency suffix
            (" 99.99 ", Decimal("99.99")),  # whitespace
        ],
    )
    def test_valid_amounts(self, value: str, expected: Decimal):
        assert _parse_amount(value) == expected

    @pytest.mark.parametrize(
        "value",
        [
            "not_a_number",
            "",
            "free",
            "'; DROP TABLE--",
        ],
    )
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
        csv = (
            "Date,Debit,Credit,Description\n"
            "2024-01-15,200.00,,Expense\n"
            "2024-01-16,,5000.00,Income\n"
        )
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
        assert len(result.rows) == 1  # only the good row
        assert len(result.errors) == 1  # one error reported

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
        for formula in [
            "=CMD('calc.exe')",
            "@SUM(1+1)*cmd|' /C calc'!A0",
            "=HYPERLINK('evil.com')",
        ]:
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


# ── to_transaction_creates_with_payees — transfer detection ──────────────────


def _parsed_row(
    counterparty_account: str = "",
    payee_name: str = "",
    amount: str = "-100.00",
    description: str = "Test",
) -> ParsedRow:
    """Build a minimal ParsedRow that mimics an mBank CSV row."""
    return ParsedRow(
        date=datetime.date(2024, 3, 15),
        amount=Decimal(amount),
        description=description,
        raw={
            "Numer rachunku": counterparty_account,
            "Nadawca/Odbiorca": payee_name,
            "Opis operacji": description,
            "Tytuł": "",
        },
    )


async def _make_account(session: AsyncSession, name: str = "Main") -> int:
    svc = AccountService(session)
    acc = await svc.create(AccountCreate(name=name, type=AccountType.CHECKING))
    return acc.id


async def _make_expense_cat(session: AsyncSession) -> int:
    svc = CategoryService(session)
    cat = await svc.create(CategoryCreate(name="Misc Expense", type=CategoryType.EXPENSE))
    return cat.id


async def _make_income_cat(session: AsyncSession) -> int:
    svc = CategoryService(session)
    cat = await svc.create(CategoryCreate(name="Misc Income", type=CategoryType.INCOME))
    return cat.id


class TestToTransactionCreatesWithPayees:
    async def test_matching_account_digits_yields_transfer(self, session: AsyncSession):
        """A row whose Numer rachunku digits are in known_account_digits → TRANSFER."""
        account_id = await _make_account(session)
        own_digits = "55114020040000330278886836"
        row = _parsed_row(counterparty_account="55 1140 2004 0000 3302 7888 6836", amount="-200.00")

        svc = ImportService(session)
        creates = await svc.to_transaction_creates_with_payees(
            [row],
            account_id=account_id,
            known_account_digits={own_digits},
        )

        assert len(creates) == 1
        assert creates[0].type == TransactionType.TRANSFER
        assert creates[0].is_internal_transfer is True

    async def test_non_matching_digits_negative_amount_yields_expense(self, session: AsyncSession):
        """A row whose Numer rachunku does NOT match known digits → EXPENSE (negative amount)."""
        account_id = await _make_account(session)
        exp_cat_id = await _make_expense_cat(session)
        row = _parsed_row(counterparty_account="99 9999 9999 9999 9999 9999 9999", amount="-50.00")

        svc = ImportService(session)
        creates = await svc.to_transaction_creates_with_payees(
            [row],
            account_id=account_id,
            default_expense_category_id=exp_cat_id,
            known_account_digits={"55114020040000330278886836"},
        )

        assert len(creates) == 1
        assert creates[0].type == TransactionType.EXPENSE
        assert creates[0].is_internal_transfer is False

    async def test_non_matching_digits_positive_amount_yields_income(self, session: AsyncSession):
        """A row with positive amount and unknown counterparty account → INCOME."""
        account_id = await _make_account(session)
        inc_cat_id = await _make_income_cat(session)
        row = _parsed_row(counterparty_account="12 3456 7890 1234 5678 9012 3456", amount="500.00")

        svc = ImportService(session)
        creates = await svc.to_transaction_creates_with_payees(
            [row],
            account_id=account_id,
            default_income_category_id=inc_cat_id,
            known_account_digits={"55114020040000330278886836"},
        )

        assert len(creates) == 1
        assert creates[0].type == TransactionType.INCOME

    async def test_empty_counterparty_account_not_transfer(self, session: AsyncSession):
        """A row with no Numer rachunku is never classified as TRANSFER."""
        account_id = await _make_account(session)
        exp_cat_id = await _make_expense_cat(session)
        row = _parsed_row(counterparty_account="", amount="-75.00")

        svc = ImportService(session)
        creates = await svc.to_transaction_creates_with_payees(
            [row],
            account_id=account_id,
            default_expense_category_id=exp_cat_id,
            known_account_digits={"55114020040000330278886836"},
        )

        assert creates[0].type == TransactionType.EXPENSE

    async def test_no_known_digits_nothing_is_transfer(self, session: AsyncSession):
        """When known_account_digits is None (or empty), no row is classified as TRANSFER."""
        account_id = await _make_account(session)
        exp_cat_id = await _make_expense_cat(session)
        row = _parsed_row(counterparty_account="55 1140 2004 0000 3302 7888 6836", amount="-100.00")

        svc = ImportService(session)
        creates = await svc.to_transaction_creates_with_payees(
            [row],
            account_id=account_id,
            default_expense_category_id=exp_cat_id,
            known_account_digits=None,
        )

        assert creates[0].type == TransactionType.EXPENSE

    async def test_transfer_amount_is_absolute(self, session: AsyncSession):
        """TRANSFER rows store abs(amount) — the original sign is stripped."""
        account_id = await _make_account(session)
        own_digits = "55114020040000330278886836"
        row = _parsed_row(
            counterparty_account="55 1140 2004 0000 3302 7888 6836",
            amount="-300.00",
        )

        svc = ImportService(session)
        creates = await svc.to_transaction_creates_with_payees(
            [row], account_id=account_id, known_account_digits={own_digits}
        )

        assert creates[0].amount == Decimal("300.00")

    async def test_payee_resolved_for_transfer_row(self, session: AsyncSession):
        """Even a TRANSFER row gets a payee_id when Nadawca/Odbiorca is set."""
        account_id = await _make_account(session)
        own_digits = "55114020040000330278886836"
        row = _parsed_row(
            counterparty_account="55 1140 2004 0000 3302 7888 6836",
            payee_name="JAN KOWALSKI",
            amount="-100.00",
        )

        svc = ImportService(session)
        creates = await svc.to_transaction_creates_with_payees(
            [row], account_id=account_id, known_account_digits={own_digits}
        )

        assert creates[0].type == TransactionType.TRANSFER
        assert creates[0].payee_id is not None

    async def test_payee_resolved_for_expense_row(self, session: AsyncSession):
        """An EXPENSE row with a known payee name gets payee_id resolved."""
        account_id = await _make_account(session)
        exp_cat_id = await _make_expense_cat(session)
        row = _parsed_row(
            counterparty_account="",
            payee_name="BIEDRONKA SP Z OO",
            amount="-42.50",
        )

        svc = ImportService(session)
        creates = await svc.to_transaction_creates_with_payees(
            [row],
            account_id=account_id,
            default_expense_category_id=exp_cat_id,
            known_account_digits=set(),
        )

        assert creates[0].payee_id is not None

    async def test_mixed_rows_correct_types(self, session: AsyncSession):
        """A batch with both internal-transfer and expense rows is classified correctly."""
        account_id = await _make_account(session)
        exp_cat_id = await _make_expense_cat(session)
        inc_cat_id = await _make_income_cat(session)
        own_digits = "55114020040000330278886836"

        transfer_row = _parsed_row(
            counterparty_account="55 1140 2004 0000 3302 7888 6836", amount="-500.00"
        )
        expense_row = _parsed_row(counterparty_account="", amount="-30.00")
        income_row = _parsed_row(counterparty_account="", amount="1000.00")

        svc = ImportService(session)
        creates = await svc.to_transaction_creates_with_payees(
            [transfer_row, expense_row, income_row],
            account_id=account_id,
            default_expense_category_id=exp_cat_id,
            default_income_category_id=inc_cat_id,
            known_account_digits={own_digits},
        )

        assert len(creates) == 3
        assert creates[0].type == TransactionType.TRANSFER
        assert creates[1].type == TransactionType.EXPENSE
        assert creates[2].type == TransactionType.INCOME

    async def test_spaces_in_account_number_stripped_for_comparison(self, session: AsyncSession):
        """Account numbers with different spacing formats still match after digit extraction."""
        account_id = await _make_account(session)
        # known digits stored without any spaces
        own_digits = "55114020040000330278886836"
        # counterparty with different spacing
        row = _parsed_row(counterparty_account="551140200400003302 78886836", amount="-10.00")

        svc = ImportService(session)
        creates = await svc.to_transaction_creates_with_payees(
            [row], account_id=account_id, known_account_digits={own_digits}
        )

        assert creates[0].type == TransactionType.TRANSFER

    async def test_empty_rows_list_returns_empty(self, session: AsyncSession):
        account_id = await _make_account(session)
        svc = ImportService(session)
        creates = await svc.to_transaction_creates_with_payees(
            [], account_id=account_id, known_account_digits={"123456"}
        )
        assert creates == []
