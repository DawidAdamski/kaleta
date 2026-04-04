"""Unit tests for AccountCreate and AccountUpdate Pydantic schemas."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from kaleta.models.account import AccountType
from kaleta.schemas.account import AccountCreate, AccountUpdate

# ── Helpers ──────────────────────────────────────────────────────────────────

SQL_PAYLOADS = [
    "'; DROP TABLE accounts; --",
    "' OR '1'='1",
    "' OR 1=1--",
    "UNION SELECT * FROM accounts--",
    "1; DELETE FROM transactions WHERE 1=1",
    "admin'--",
    "' AND SLEEP(5)--",
    "'; INSERT INTO accounts VALUES ('hacked')--",
]

XSS_PAYLOADS = [
    "<script>alert('xss')</script>",
    "javascript:alert(1)",
    '"><img src=x onerror=alert(1)>',
    "<svg onload=alert(1)>",
    "';alert('xss');//",
]


# ── AccountCreate ─────────────────────────────────────────────────────────────


class TestAccountCreate:
    def test_valid_minimal(self):
        schema = AccountCreate(name="PKO Główne")
        assert schema.name == "PKO Główne"
        assert schema.type == AccountType.CHECKING
        assert schema.balance == Decimal("0.00")

    def test_valid_all_fields(self):
        schema = AccountCreate(
            name="Oszczędności",
            type=AccountType.SAVINGS,
            balance=Decimal("5000.00"),
        )
        assert schema.type == AccountType.SAVINGS
        assert schema.balance == Decimal("5000.00")

    def test_all_account_types_accepted(self):
        for account_type in AccountType:
            s = AccountCreate(name="Test", type=account_type)
            assert s.type == account_type

    def test_name_empty_string_rejected(self):
        with pytest.raises(ValidationError, match="string_too_short"):
            AccountCreate(name="")

    def test_name_too_long_rejected(self):
        with pytest.raises(ValidationError, match="string_too_long"):
            AccountCreate(name="x" * 101)

    def test_name_exactly_max_length_accepted(self):
        schema = AccountCreate(name="x" * 100)
        assert len(schema.name) == 100

    def test_name_missing_rejected(self):
        with pytest.raises(ValidationError):
            AccountCreate()  # type: ignore[call-arg]

    def test_invalid_account_type_rejected(self):
        with pytest.raises(ValidationError):
            AccountCreate(name="Test", type="invalid_type")

    def test_negative_balance_allowed(self):
        """Credit accounts legitimately have negative balances."""
        schema = AccountCreate(name="Visa", type=AccountType.CREDIT, balance=Decimal("-1500.00"))
        assert schema.balance == Decimal("-1500.00")

    def test_balance_wrong_type_rejected(self):
        with pytest.raises(ValidationError):
            AccountCreate(name="Test", balance="not_a_number")  # type: ignore[arg-type]

    @pytest.mark.parametrize("payload", SQL_PAYLOADS)
    def test_sql_injection_in_name_accepted_as_plain_text(self, payload: str):
        """SQL injection strings must be stored verbatim — ORM parameterises queries."""
        truncated = payload[:100]
        schema = AccountCreate(name=truncated)
        assert schema.name == truncated

    @pytest.mark.parametrize("payload", XSS_PAYLOADS)
    def test_xss_in_name_accepted_as_plain_text(self, payload: str):
        """XSS payloads are stored verbatim; the UI layer is responsible for escaping."""
        truncated = payload[:100]
        schema = AccountCreate(name=truncated)
        assert schema.name == truncated


# ── AccountUpdate ─────────────────────────────────────────────────────────────


class TestAccountUpdate:
    def test_all_fields_optional(self):
        schema = AccountUpdate()
        assert schema.name is None
        assert schema.type is None
        assert schema.balance is None

    def test_partial_update(self):
        schema = AccountUpdate(name="New Name")
        assert schema.name == "New Name"
        assert schema.type is None

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError, match="string_too_short"):
            AccountUpdate(name="")

    def test_invalid_type_rejected(self):
        with pytest.raises(ValidationError):
            AccountUpdate(type="bogus")  # type: ignore[arg-type]

    @pytest.mark.parametrize("payload", SQL_PAYLOADS)
    def test_sql_injection_in_name_update(self, payload: str):
        schema = AccountUpdate(name=payload[:100])
        assert schema.name == payload[:100]


# ── Currency field — AccountCreate ────────────────────────────────────────────


class TestAccountCreateCurrency:
    def test_currency_defaults_to_pln(self):
        schema = AccountCreate(name="Test")
        assert schema.currency == "PLN"

    def test_currency_explicit_eur(self):
        schema = AccountCreate(name="Euro Account", currency="EUR")
        assert schema.currency == "EUR"

    def test_currency_explicit_usd(self):
        schema = AccountCreate(name="Dollar Account", currency="USD")
        assert schema.currency == "USD"

    def test_currency_must_be_exactly_3_chars(self):
        schema = AccountCreate(name="Test", currency="GBP")
        assert schema.currency == "GBP"

    def test_currency_too_short_rejected(self):
        with pytest.raises(ValidationError, match="string_too_short"):
            AccountCreate(name="Test", currency="PL")

    def test_currency_too_long_rejected(self):
        with pytest.raises(ValidationError, match="string_too_long"):
            AccountCreate(name="Test", currency="EURO")

    def test_currency_empty_rejected(self):
        with pytest.raises(ValidationError, match="string_too_short"):
            AccountCreate(name="Test", currency="")

    def test_currency_integer_rejected(self):
        with pytest.raises(ValidationError):
            AccountCreate(name="Test", currency=123)  # type: ignore[arg-type]


# ── Currency field — AccountUpdate ────────────────────────────────────────────


class TestAccountUpdateCurrency:
    def test_currency_defaults_to_none(self):
        schema = AccountUpdate()
        assert schema.currency is None

    def test_currency_explicit_usd(self):
        schema = AccountUpdate(currency="USD")
        assert schema.currency == "USD"

    def test_currency_explicit_eur(self):
        schema = AccountUpdate(currency="EUR")
        assert schema.currency == "EUR"

    def test_currency_too_short_rejected(self):
        with pytest.raises(ValidationError, match="string_too_short"):
            AccountUpdate(currency="EU")

    def test_currency_too_long_rejected(self):
        with pytest.raises(ValidationError, match="string_too_long"):
            AccountUpdate(currency="EURO")
