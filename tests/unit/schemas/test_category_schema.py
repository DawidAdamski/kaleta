"""Unit tests for CategoryCreate and CategoryUpdate Pydantic schemas."""

import pytest
from pydantic import ValidationError

from kaleta.models.category import CategoryType
from kaleta.schemas.category import CategoryCreate, CategoryUpdate

SQL_PAYLOADS = [
    "'; DROP TABLE categories; --",
    "' OR 1=1--",
    "UNION SELECT name FROM categories--",
    "1'; DELETE FROM categories; --",
]

XSS_PAYLOADS = [
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    "';alert('xss')//",
]


class TestCategoryCreate:
    def test_valid_expense(self):
        schema = CategoryCreate(name="Żywność", type=CategoryType.EXPENSE)
        assert schema.name == "Żywność"
        assert schema.type == CategoryType.EXPENSE

    def test_valid_income(self):
        schema = CategoryCreate(name="Wynagrodzenie", type=CategoryType.INCOME)
        assert schema.type == CategoryType.INCOME

    def test_name_required(self):
        with pytest.raises(ValidationError):
            CategoryCreate(name="", type=CategoryType.EXPENSE)

    def test_name_too_long_rejected(self):
        with pytest.raises(ValidationError, match="string_too_long"):
            CategoryCreate(name="x" * 101, type=CategoryType.EXPENSE)

    def test_type_required(self):
        with pytest.raises(ValidationError):
            CategoryCreate(name="Test")  # type: ignore[call-arg]

    def test_invalid_type_rejected(self):
        with pytest.raises(ValidationError):
            CategoryCreate(name="Test", type="transfer")  # transfer is not a CategoryType

    @pytest.mark.parametrize("payload", SQL_PAYLOADS)
    def test_sql_injection_stored_as_plain_text(self, payload: str):
        schema = CategoryCreate(name=payload[:100], type=CategoryType.EXPENSE)
        assert schema.name == payload[:100]

    @pytest.mark.parametrize("payload", XSS_PAYLOADS)
    def test_xss_stored_as_plain_text(self, payload: str):
        schema = CategoryCreate(name=payload[:100], type=CategoryType.EXPENSE)
        assert schema.name == payload[:100]


class TestCategoryUpdate:
    def test_all_fields_optional(self):
        schema = CategoryUpdate()
        assert schema.name is None
        assert schema.type is None

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            CategoryUpdate(name="")

    def test_invalid_type_rejected(self):
        with pytest.raises(ValidationError):
            CategoryUpdate(type="bogus")  # type: ignore[arg-type]

    @pytest.mark.parametrize("payload", SQL_PAYLOADS)
    def test_sql_injection_in_update(self, payload: str):
        schema = CategoryUpdate(name=payload[:100])
        assert schema.name == payload[:100]
