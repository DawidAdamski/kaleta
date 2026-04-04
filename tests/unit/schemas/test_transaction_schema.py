"""Unit tests for TransactionCreate and TransactionUpdate Pydantic schemas."""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from kaleta.models.transaction import TransactionType
from kaleta.schemas.transaction import TransactionCreate, TransactionUpdate

SQL_PAYLOADS = [
    "'; DROP TABLE transactions; --",
    "' OR 1=1--",
    "UNION SELECT * FROM accounts--",
    "1; DELETE FROM transactions",
    "' AND SLEEP(5)--",
]

XSS_PAYLOADS = [
    "<script>alert('xss')</script>",
    '"><img src=x onerror=alert(1)>',
    "<svg onload=alert(document.cookie)>",
]

TODAY = datetime.date.today()


def _base(**kwargs) -> dict:
    defaults = dict(
        account_id=1,
        category_id=1,
        amount=Decimal("100.00"),
        type=TransactionType.EXPENSE,
        date=TODAY,
        description="Test transaction",
    )
    defaults.update(kwargs)
    return defaults


class TestTransactionCreate:
    def test_valid_expense(self):
        schema = TransactionCreate(**_base())
        assert schema.amount == Decimal("100.00")
        assert schema.type == TransactionType.EXPENSE

    def test_valid_income(self):
        schema = TransactionCreate(**_base(type=TransactionType.INCOME, category_id=2))
        assert schema.type == TransactionType.INCOME

    def test_valid_internal_transfer(self):
        schema = TransactionCreate(
            account_id=1,
            category_id=None,
            amount=Decimal("500.00"),
            type=TransactionType.TRANSFER,
            date=TODAY,
            description="Transfer",
            is_internal_transfer=True,
            linked_transaction_id=None,
        )
        assert schema.is_internal_transfer is True

    # ── Required field validation ──────────────────────────────────────────

    def test_account_id_required(self):
        data = _base()
        del data["account_id"]
        with pytest.raises(ValidationError):
            TransactionCreate(**data)  # type: ignore[arg-type]

    def test_amount_required(self):
        data = _base()
        del data["amount"]
        with pytest.raises(ValidationError):
            TransactionCreate(**data)  # type: ignore[arg-type]

    def test_date_required(self):
        data = _base()
        del data["date"]
        with pytest.raises(ValidationError):
            TransactionCreate(**data)  # type: ignore[arg-type]

    def test_type_required(self):
        data = _base()
        del data["type"]
        with pytest.raises(ValidationError):
            TransactionCreate(**data)  # type: ignore[arg-type]

    # ── Type validation ────────────────────────────────────────────────────

    def test_invalid_transaction_type_rejected(self):
        with pytest.raises(ValidationError):
            TransactionCreate(**_base(type="payment"))

    def test_invalid_date_string_rejected(self):
        with pytest.raises(ValidationError):
            TransactionCreate(**_base(date="not-a-date"))  # type: ignore[arg-type]

    def test_amount_non_numeric_rejected(self):
        with pytest.raises(ValidationError):
            TransactionCreate(**_base(amount="free"))  # type: ignore[arg-type]

    def test_account_id_non_integer_rejected(self):
        with pytest.raises(ValidationError):
            TransactionCreate(**_base(account_id="one"))  # type: ignore[arg-type]

    def test_description_too_long_rejected(self):
        with pytest.raises(ValidationError, match="string_too_long"):
            TransactionCreate(**_base(description="x" * 501))

    def test_description_exactly_500_chars_accepted(self):
        schema = TransactionCreate(**_base(description="x" * 500))
        assert len(schema.description) == 500

    # ── Business rule validators ───────────────────────────────────────────

    def test_expense_without_category_rejected(self):
        with pytest.raises(ValidationError, match="category"):
            TransactionCreate(**_base(category_id=None, type=TransactionType.EXPENSE))

    def test_income_without_category_rejected(self):
        with pytest.raises(ValidationError, match="category"):
            TransactionCreate(**_base(category_id=None, type=TransactionType.INCOME))

    def test_transfer_without_category_allowed(self):
        schema = TransactionCreate(
            **_base(
                category_id=None,
                type=TransactionType.TRANSFER,
                is_internal_transfer=True,
            )
        )
        assert schema.category_id is None

    def test_internal_transfer_with_wrong_type_rejected(self):
        with pytest.raises(ValidationError, match="type"):
            TransactionCreate(
                **_base(
                    type=TransactionType.EXPENSE,
                    is_internal_transfer=True,
                )
            )

    # ── Security ──────────────────────────────────────────────────────────

    @pytest.mark.parametrize("payload", SQL_PAYLOADS)
    def test_sql_injection_in_description_stored_verbatim(self, payload: str):
        schema = TransactionCreate(**_base(description=payload[:500]))
        assert schema.description == payload[:500]

    @pytest.mark.parametrize("payload", XSS_PAYLOADS)
    def test_xss_in_description_stored_verbatim(self, payload: str):
        schema = TransactionCreate(**_base(description=payload[:500]))
        assert schema.description == payload[:500]

    def test_null_byte_in_description(self):
        """Null bytes are accepted at schema level; DB layer handles them."""
        payload = "normal\x00evil"
        schema = TransactionCreate(**_base(description=payload))
        assert schema.description == payload

    def test_very_large_amount_accepted(self):
        """No artificial upper cap on amount at schema level."""
        schema = TransactionCreate(**_base(amount=Decimal("999999999999999.99")))
        assert schema.amount == Decimal("999999999999999.99")

    def test_future_date_accepted(self):
        future = datetime.date.today() + datetime.timedelta(days=365)
        schema = TransactionCreate(**_base(date=future))
        assert schema.date == future

    def test_very_old_date_accepted(self):
        old = datetime.date(1990, 1, 1)
        schema = TransactionCreate(**_base(date=old))
        assert schema.date == old


# ── exchange_rate field ────────────────────────────────────────────────────────


class TestTransactionExchangeRate:
    def test_exchange_rate_defaults_to_none(self):
        schema = TransactionCreate(
            account_id=1,
            category_id=1,
            amount=Decimal("100.00"),
            type=TransactionType.EXPENSE,
            date=TODAY,
        )
        assert schema.exchange_rate is None

    def test_exchange_rate_none_is_accepted(self):
        schema = TransactionCreate(**_base(exchange_rate=None))
        assert schema.exchange_rate is None

    def test_exchange_rate_positive_decimal_accepted(self):
        schema = TransactionCreate(**_base(exchange_rate=Decimal("4.250000")))
        assert schema.exchange_rate == Decimal("4.250000")

    def test_exchange_rate_on_transfer_accepted(self):
        schema = TransactionCreate(
            account_id=1,
            category_id=None,
            amount=Decimal("500.00"),
            type=TransactionType.TRANSFER,
            date=TODAY,
            description="Cross-currency transfer",
            is_internal_transfer=True,
            exchange_rate=Decimal("4.25"),
        )
        assert schema.exchange_rate == Decimal("4.25")
        assert schema.is_internal_transfer is True

    def test_exchange_rate_non_numeric_string_rejected(self):
        with pytest.raises(ValidationError):
            TransactionCreate(**_base(exchange_rate="not-a-number"))  # type: ignore[arg-type]

    def test_exchange_rate_small_fractional_accepted(self):
        schema = TransactionCreate(**_base(exchange_rate=Decimal("0.000001")))
        assert schema.exchange_rate == Decimal("0.000001")

    def test_exchange_rate_large_value_accepted(self):
        schema = TransactionCreate(**_base(exchange_rate=Decimal("999999999.123456")))
        assert schema.exchange_rate == Decimal("999999999.123456")


class TestTransactionUpdate:
    def test_all_optional(self):
        schema = TransactionUpdate()
        assert schema.amount is None
        assert schema.type is None
        assert schema.date is None
        assert schema.description is None

    def test_partial_update(self):
        schema = TransactionUpdate(amount=Decimal("200.00"))
        assert schema.amount == Decimal("200.00")
        assert schema.type is None

    def test_invalid_type_rejected(self):
        with pytest.raises(ValidationError):
            TransactionUpdate(type="bogus")  # type: ignore[arg-type]

    def test_description_too_long_rejected(self):
        with pytest.raises(ValidationError):
            TransactionUpdate(description="x" * 501)

    @pytest.mark.parametrize("payload", SQL_PAYLOADS)
    def test_sql_injection_in_update(self, payload: str):
        schema = TransactionUpdate(description=payload[:500])
        assert schema.description == payload[:500]
