"""Unit tests for Payee Pydantic schemas — no DB needed."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from kaleta.schemas.payee import PayeeCreate, PayeeResponse, PayeeUpdate


class TestPayeeCreate:
    def test_minimal_valid(self):
        schema = PayeeCreate(name="Biedronka")
        assert schema.name == "Biedronka"
        assert schema.website is None
        assert schema.address is None
        assert schema.city is None
        assert schema.country is None
        assert schema.email is None
        assert schema.phone is None
        assert schema.notes is None

    def test_all_fields_populated(self):
        schema = PayeeCreate(
            name="Żabka",
            website="https://zabka.pl",
            address="ul. Długa 5",
            city="Warszawa",
            country="Poland",
            email="kontakt@zabka.pl",
            phone="+48 22 123 45 67",
            notes="Convenience store",
        )
        assert schema.name == "Żabka"
        assert schema.website == "https://zabka.pl"
        assert schema.address == "ul. Długa 5"
        assert schema.city == "Warszawa"
        assert schema.country == "Poland"
        assert schema.email == "kontakt@zabka.pl"
        assert schema.phone == "+48 22 123 45 67"
        assert schema.notes == "Convenience store"

    def test_name_empty_string_rejected(self):
        with pytest.raises(ValidationError, match="string_too_short"):
            PayeeCreate(name="")

    def test_name_too_long_rejected(self):
        with pytest.raises(ValidationError, match="string_too_long"):
            PayeeCreate(name="x" * 201)

    def test_website_too_long_rejected(self):
        with pytest.raises(ValidationError, match="string_too_long"):
            PayeeCreate(name="Test", website="h" * 501)

    def test_address_too_long_rejected(self):
        with pytest.raises(ValidationError, match="string_too_long"):
            PayeeCreate(name="Test", address="a" * 301)

    def test_city_too_long_rejected(self):
        with pytest.raises(ValidationError, match="string_too_long"):
            PayeeCreate(name="Test", city="c" * 101)

    def test_country_too_long_rejected(self):
        with pytest.raises(ValidationError, match="string_too_long"):
            PayeeCreate(name="Test", country="c" * 101)

    def test_email_too_long_rejected(self):
        with pytest.raises(ValidationError, match="string_too_long"):
            PayeeCreate(name="Test", email="e" * 201)

    def test_phone_too_long_rejected(self):
        with pytest.raises(ValidationError, match="string_too_long"):
            PayeeCreate(name="Test", phone="p" * 51)

    def test_notes_too_long_rejected(self):
        with pytest.raises(ValidationError, match="string_too_long"):
            PayeeCreate(name="Test", notes="n" * 501)

    def test_optional_fields_accept_none_explicitly(self):
        schema = PayeeCreate(
            name="NoneFields",
            website=None,
            address=None,
            city=None,
            country=None,
            email=None,
            phone=None,
            notes=None,
        )
        assert schema.website is None
        assert schema.city is None

    @pytest.mark.parametrize(
        "payload",
        [
            "'; DROP TABLE payees; --",
            "' OR '1'='1",
            "UNION SELECT password FROM users--",
        ],
    )
    def test_sql_injection_accepted_in_name(self, payload: str):
        schema = PayeeCreate(name=payload[:200])
        assert schema.name == payload[:200]

    @pytest.mark.parametrize(
        "payload",
        [
            "<script>alert('xss')</script>",
            "javascript:alert(document.cookie)",
            '"><img src=x onerror=alert(1)>',
        ],
    )
    def test_xss_accepted_in_text_fields(self, payload: str):
        schema = PayeeCreate(name="Test", notes=payload[:500])
        assert schema.notes == payload[:500]

    @pytest.mark.parametrize(
        "payload",
        [
            "'; DROP TABLE payees; --",
            "<script>alert(1)</script>",
        ],
    )
    def test_injection_accepted_in_new_optional_fields(self, payload: str):
        schema = PayeeCreate(
            name="InjectionTest",
            website=payload[:500],
            address=payload[:300],
            city=payload[:100],
            country=payload[:100],
            email=payload[:200],
            phone=payload[:50],
        )
        assert schema.website == payload[:500]
        assert schema.address == payload[:300]
        assert schema.city == payload[:100]
        assert schema.country == payload[:100]
        assert schema.email == payload[:200]
        assert schema.phone == payload[:50]


class TestPayeeUpdate:
    def test_fully_empty_update_is_valid(self):
        schema = PayeeUpdate()
        assert schema.name is None
        assert schema.website is None
        assert schema.city is None

    def test_update_all_new_fields(self):
        schema = PayeeUpdate(
            website="https://new.com",
            address="New Road 1",
            city="Łódź",
            country="Poland",
            email="new@new.com",
            phone="000111222",
        )
        assert schema.website == "https://new.com"
        assert schema.address == "New Road 1"
        assert schema.city == "Łódź"
        assert schema.country == "Poland"
        assert schema.email == "new@new.com"
        assert schema.phone == "000111222"

    def test_update_name_empty_string_rejected(self):
        with pytest.raises(ValidationError, match="string_too_short"):
            PayeeUpdate(name="")

    def test_update_website_too_long_rejected(self):
        with pytest.raises(ValidationError, match="string_too_long"):
            PayeeUpdate(website="h" * 501)

    def test_update_city_too_long_rejected(self):
        with pytest.raises(ValidationError, match="string_too_long"):
            PayeeUpdate(city="c" * 101)

    def test_update_country_too_long_rejected(self):
        with pytest.raises(ValidationError, match="string_too_long"):
            PayeeUpdate(country="c" * 101)

    def test_update_email_too_long_rejected(self):
        with pytest.raises(ValidationError, match="string_too_long"):
            PayeeUpdate(email="e" * 201)

    def test_update_phone_too_long_rejected(self):
        with pytest.raises(ValidationError, match="string_too_long"):
            PayeeUpdate(phone="p" * 51)

    def test_model_dump_exclude_unset_omits_untouched_fields(self):
        schema = PayeeUpdate(city="Kraków")
        dumped = schema.model_dump(exclude_unset=True)
        assert dumped == {"city": "Kraków"}
        assert "name" not in dumped
        assert "website" not in dumped


class TestPayeeResponse:
    def test_from_orm_attributes(self):
        from datetime import datetime

        class _FakePayee:
            id = 1
            name = "Lidl"
            website = "https://lidl.pl"
            address = "Lidl Street 1"
            city = "Gdańsk"
            country = "Poland"
            email = "pl@lidl.com"
            phone = "+48 58 000 0000"
            notes = "Discount"
            created_at = datetime(2024, 1, 1, 12, 0, 0)
            updated_at = datetime(2024, 6, 1, 12, 0, 0)

        resp = PayeeResponse.model_validate(_FakePayee())
        assert resp.id == 1
        assert resp.name == "Lidl"
        assert resp.website == "https://lidl.pl"
        assert resp.address == "Lidl Street 1"
        assert resp.city == "Gdańsk"
        assert resp.country == "Poland"
        assert resp.email == "pl@lidl.com"
        assert resp.phone == "+48 58 000 0000"
        assert resp.notes == "Discount"

    def test_from_orm_with_nulls(self):
        from datetime import datetime

        class _FakePayeeNulls:
            id = 2
            name = "MinimalPayee"
            website = None
            address = None
            city = None
            country = None
            email = None
            phone = None
            notes = None
            created_at = datetime(2024, 1, 1)
            updated_at = datetime(2024, 1, 1)

        resp = PayeeResponse.model_validate(_FakePayeeNulls())
        assert resp.website is None
        assert resp.address is None
        assert resp.city is None
        assert resp.country is None
        assert resp.email is None
        assert resp.phone is None
