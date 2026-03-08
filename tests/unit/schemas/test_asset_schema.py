"""Unit tests for AssetCreate, AssetUpdate, and AssetResponse Pydantic schemas."""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from kaleta.models.asset import AssetType
from kaleta.schemas.asset import AssetCreate, AssetUpdate

SQL_PAYLOADS = [
    "'; DROP TABLE assets; --",
    "' OR '1'='1",
    "UNION SELECT password FROM users--",
    "1; DELETE FROM assets WHERE 1=1",
    "' AND SLEEP(5)--",
]

XSS_PAYLOADS = [
    "<script>alert('xss')</script>",
    "javascript:alert(document.cookie)",
    '"><img src=x onerror=alert(1)>',
    "<svg/onload=alert(1)>",
]


# ── AssetType enum ─────────────────────────────────────────────────────────────


class TestAssetTypeEnum:

    def test_real_estate_value(self):
        assert AssetType.REAL_ESTATE.value == "real_estate"

    def test_vehicle_value(self):
        assert AssetType.VEHICLE.value == "vehicle"

    def test_valuables_value(self):
        assert AssetType.VALUABLES.value == "valuables"

    def test_other_value(self):
        assert AssetType.OTHER.value == "other"

    def test_all_four_members_exist(self):
        members = {t.value for t in AssetType}
        assert members == {"real_estate", "vehicle", "valuables", "other"}


# ── AssetCreate ───────────────────────────────────────────────────────────────


class TestAssetCreate:

    def test_valid_minimal(self):
        schema = AssetCreate(name="House")
        assert schema.name == "House"
        assert schema.type == AssetType.OTHER
        assert schema.value == Decimal("0.00")
        assert schema.description == ""
        assert schema.purchase_date is None
        assert schema.purchase_price is None

    def test_valid_all_fields(self):
        schema = AssetCreate(
            name="Family Car",
            type=AssetType.VEHICLE,
            value=Decimal("25000.00"),
            description="2021 Toyota Corolla",
            purchase_date=datetime.date(2021, 6, 15),
            purchase_price=Decimal("27000.00"),
        )
        assert schema.name == "Family Car"
        assert schema.type == AssetType.VEHICLE
        assert schema.value == Decimal("25000.00")
        assert schema.description == "2021 Toyota Corolla"
        assert schema.purchase_date == datetime.date(2021, 6, 15)
        assert schema.purchase_price == Decimal("27000.00")

    def test_all_asset_types_accepted(self):
        for asset_type in AssetType:
            s = AssetCreate(name="Test", type=asset_type)
            assert s.type == asset_type

    def test_name_empty_string_rejected(self):
        with pytest.raises(ValidationError, match="string_too_short"):
            AssetCreate(name="")

    def test_name_too_long_rejected(self):
        with pytest.raises(ValidationError, match="string_too_long"):
            AssetCreate(name="x" * 101)

    def test_name_exactly_100_chars_accepted(self):
        schema = AssetCreate(name="x" * 100)
        assert len(schema.name) == 100

    def test_name_missing_rejected(self):
        with pytest.raises(ValidationError):
            AssetCreate()  # type: ignore[call-arg]

    def test_invalid_type_rejected(self):
        with pytest.raises(ValidationError, match="enum"):
            AssetCreate(name="Test", type="spaceship")

    def test_value_defaults_to_zero(self):
        schema = AssetCreate(name="Painting")
        assert schema.value == Decimal("0.00")

    def test_value_wrong_type_rejected(self):
        with pytest.raises(ValidationError):
            AssetCreate(name="Test", value="not_a_number")  # type: ignore[arg-type]

    def test_purchase_price_optional_none_by_default(self):
        schema = AssetCreate(name="Ring")
        assert schema.purchase_price is None

    def test_purchase_date_optional_none_by_default(self):
        schema = AssetCreate(name="Ring")
        assert schema.purchase_date is None

    @pytest.mark.parametrize("payload", SQL_PAYLOADS)
    def test_sql_injection_in_name_accepted_as_plain_text(self, payload: str):
        truncated = payload[:100]
        schema = AssetCreate(name=truncated)
        assert schema.name == truncated

    @pytest.mark.parametrize("payload", XSS_PAYLOADS)
    def test_xss_in_name_accepted_as_plain_text(self, payload: str):
        truncated = payload[:100]
        schema = AssetCreate(name=truncated)
        assert schema.name == truncated

    @pytest.mark.parametrize("payload", SQL_PAYLOADS)
    def test_sql_injection_in_description_accepted_as_plain_text(self, payload: str):
        truncated = payload[:500]
        schema = AssetCreate(name="Test", description=truncated)
        assert schema.description == truncated

    @pytest.mark.parametrize("payload", XSS_PAYLOADS)
    def test_xss_in_description_accepted_as_plain_text(self, payload: str):
        schema = AssetCreate(name="Test", description=payload)
        assert schema.description == payload

    def test_type_string_value_accepted(self):
        """AssetType is a str enum — string values are valid."""
        schema = AssetCreate(name="Land", type="real_estate")
        assert schema.type == AssetType.REAL_ESTATE

    def test_type_integer_rejected(self):
        with pytest.raises(ValidationError):
            AssetCreate(name="Test", type=42)  # type: ignore[arg-type]


# ── AssetUpdate ───────────────────────────────────────────────────────────────


class TestAssetUpdate:

    def test_all_fields_optional(self):
        schema = AssetUpdate()
        assert schema.name is None
        assert schema.type is None
        assert schema.value is None
        assert schema.description is None
        assert schema.purchase_date is None
        assert schema.purchase_price is None

    def test_partial_update_name_only(self):
        schema = AssetUpdate(name="New Name")
        assert schema.name == "New Name"
        assert schema.type is None

    def test_partial_update_value_only(self):
        schema = AssetUpdate(value=Decimal("50000.00"))
        assert schema.value == Decimal("50000.00")
        assert schema.name is None

    def test_partial_update_type(self):
        schema = AssetUpdate(type=AssetType.REAL_ESTATE)
        assert schema.type == AssetType.REAL_ESTATE

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError, match="string_too_short"):
            AssetUpdate(name="")

    def test_name_too_long_rejected(self):
        with pytest.raises(ValidationError, match="string_too_long"):
            AssetUpdate(name="x" * 101)

    def test_invalid_type_rejected(self):
        with pytest.raises(ValidationError, match="enum"):
            AssetUpdate(type="airplane")  # type: ignore[arg-type]

    @pytest.mark.parametrize("payload", SQL_PAYLOADS)
    def test_sql_injection_in_name_update(self, payload: str):
        schema = AssetUpdate(name=payload[:100])
        assert schema.name == payload[:100]

    @pytest.mark.parametrize("payload", XSS_PAYLOADS)
    def test_xss_in_name_update(self, payload: str):
        schema = AssetUpdate(name=payload[:100])
        assert schema.name == payload[:100]

    def test_update_purchase_date_to_none(self):
        schema = AssetUpdate(purchase_date=None)
        assert schema.purchase_date is None

    def test_update_purchase_price(self):
        schema = AssetUpdate(purchase_price=Decimal("15000.00"))
        assert schema.purchase_price == Decimal("15000.00")
