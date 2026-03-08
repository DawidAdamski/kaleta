"""Unit tests for InstitutionCreate and InstitutionUpdate Pydantic schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from kaleta.models.institution import InstitutionType
from kaleta.schemas.institution import InstitutionCreate, InstitutionUpdate


# ── Helpers ───────────────────────────────────────────────────────────────────

SQL_PAYLOADS = [
    "'; DROP TABLE institutions; --",
    "' OR '1'='1",
    "UNION SELECT name FROM institutions--",
    "1; DELETE FROM institutions WHERE 1=1",
    "' AND SLEEP(5)--",
    "'; INSERT INTO institutions VALUES ('hacked')--",
]

XSS_PAYLOADS = [
    "<script>alert('xss')</script>",
    "javascript:alert(document.cookie)",
    '"><img src=x onerror=alert(1)>',
    "<svg/onload=alert(1)>",
    "';alert('xss');//",
]


# ── InstitutionCreate ──────────────────────────────────────────────────────────

class TestInstitutionCreate:

    def test_valid_minimal(self):
        schema = InstitutionCreate(name="PKO Bank Polski")
        assert schema.name == "PKO Bank Polski"
        assert schema.type == InstitutionType.BANK

    def test_valid_all_fields(self):
        schema = InstitutionCreate(
            name="Revolut",
            type=InstitutionType.FINTECH,
            color="#FF5733",
            website="https://revolut.com",
            description="Digital bank and financial app.",
        )
        assert schema.type == InstitutionType.FINTECH
        assert schema.color == "#FF5733"
        assert schema.website == "https://revolut.com"
        assert schema.description == "Digital bank and financial app."

    def test_all_institution_types_accepted(self):
        for institution_type in InstitutionType:
            s = InstitutionCreate(name="Test", type=institution_type)
            assert s.type == institution_type

    def test_optional_fields_default_to_none(self):
        schema = InstitutionCreate(name="Test Bank")
        assert schema.color is None
        assert schema.website is None
        assert schema.description is None

    def test_name_empty_string_rejected(self):
        with pytest.raises(ValidationError, match="string_too_short"):
            InstitutionCreate(name="")

    def test_name_too_long_rejected(self):
        with pytest.raises(ValidationError, match="string_too_long"):
            InstitutionCreate(name="x" * 101)

    def test_name_exactly_max_length_accepted(self):
        schema = InstitutionCreate(name="x" * 100)
        assert len(schema.name) == 100

    def test_name_missing_rejected(self):
        with pytest.raises(ValidationError):
            InstitutionCreate()  # type: ignore[call-arg]

    def test_invalid_type_rejected(self):
        with pytest.raises(ValidationError, match="enum"):
            InstitutionCreate(name="Test", type="invalid_type")  # type: ignore[arg-type]

    def test_color_too_long_rejected(self):
        with pytest.raises(ValidationError, match="string_too_long"):
            InstitutionCreate(name="Test", color="#1234567890")

    def test_color_exactly_max_length_accepted(self):
        schema = InstitutionCreate(name="Test", color="#1976d2")
        assert schema.color == "#1976d2"

    def test_website_too_long_rejected(self):
        with pytest.raises(ValidationError, match="string_too_long"):
            InstitutionCreate(name="Test", website="https://" + "x" * 200)

    def test_description_too_long_rejected(self):
        with pytest.raises(ValidationError, match="string_too_long"):
            InstitutionCreate(name="Test", description="x" * 501)

    def test_description_exactly_max_length_accepted(self):
        schema = InstitutionCreate(name="Test", description="x" * 500)
        assert len(schema.description) == 500  # type: ignore[arg-type]

    @pytest.mark.parametrize("payload", SQL_PAYLOADS)
    def test_sql_injection_in_name_accepted_as_plain_text(self, payload: str):
        """SQL injection strings must be stored verbatim — ORM parameterises queries."""
        truncated = payload[:100]
        schema = InstitutionCreate(name=truncated)
        assert schema.name == truncated

    @pytest.mark.parametrize("payload", XSS_PAYLOADS)
    def test_xss_in_name_accepted_as_plain_text(self, payload: str):
        """XSS payloads are stored verbatim; the UI layer is responsible for escaping."""
        truncated = payload[:100]
        schema = InstitutionCreate(name=truncated)
        assert schema.name == truncated

    @pytest.mark.parametrize("payload", SQL_PAYLOADS)
    def test_sql_injection_in_description_accepted_as_plain_text(self, payload: str):
        truncated = payload[:500]
        schema = InstitutionCreate(name="Test", description=truncated)
        assert schema.description == truncated

    @pytest.mark.parametrize("payload", XSS_PAYLOADS)
    def test_xss_in_description_accepted_as_plain_text(self, payload: str):
        truncated = payload[:500]
        schema = InstitutionCreate(name="Test", description=truncated)
        assert schema.description == truncated


# ── InstitutionUpdate ──────────────────────────────────────────────────────────

class TestInstitutionUpdate:

    def test_all_fields_optional(self):
        schema = InstitutionUpdate()
        assert schema.name is None
        assert schema.type is None
        assert schema.color is None
        assert schema.website is None
        assert schema.description is None

    def test_partial_update_name_only(self):
        schema = InstitutionUpdate(name="New Name")
        assert schema.name == "New Name"
        assert schema.type is None

    def test_partial_update_type_only(self):
        schema = InstitutionUpdate(type=InstitutionType.BROKER)
        assert schema.type == InstitutionType.BROKER
        assert schema.name is None

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError, match="string_too_short"):
            InstitutionUpdate(name="")

    def test_name_too_long_rejected(self):
        with pytest.raises(ValidationError, match="string_too_long"):
            InstitutionUpdate(name="x" * 101)

    def test_invalid_type_rejected(self):
        with pytest.raises(ValidationError, match="enum"):
            InstitutionUpdate(type="bogus")  # type: ignore[arg-type]

    def test_color_too_long_rejected(self):
        with pytest.raises(ValidationError, match="string_too_long"):
            InstitutionUpdate(color="#1234567890")

    def test_description_too_long_rejected(self):
        with pytest.raises(ValidationError, match="string_too_long"):
            InstitutionUpdate(description="x" * 501)

    @pytest.mark.parametrize("payload", SQL_PAYLOADS)
    def test_sql_injection_in_name_update(self, payload: str):
        schema = InstitutionUpdate(name=payload[:100])
        assert schema.name == payload[:100]

    @pytest.mark.parametrize("payload", XSS_PAYLOADS)
    def test_xss_in_name_update(self, payload: str):
        schema = InstitutionUpdate(name=payload[:100])
        assert schema.name == payload[:100]
