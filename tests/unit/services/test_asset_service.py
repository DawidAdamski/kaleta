"""Unit tests for AssetService — uses in-memory SQLite."""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.asset import AssetType
from kaleta.schemas.asset import AssetCreate, AssetUpdate
from kaleta.services.asset_service import AssetService
from kaleta.services.net_worth_service import NetWorthService, PhysicalAssetSnapshot

SQL_INJECTIONS = [
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


@pytest.fixture
def svc(session: AsyncSession) -> AssetService:
    return AssetService(session)


# ── Create ─────────────────────────────────────────────────────────────────────


class TestAssetServiceCreate:
    async def test_create_returns_asset_with_id(self, svc: AssetService):
        asset = await svc.create(AssetCreate(name="House"))
        assert asset.id is not None
        assert asset.name == "House"

    async def test_create_sets_default_type(self, svc: AssetService):
        asset = await svc.create(AssetCreate(name="Mystery Item"))
        assert asset.type == AssetType.OTHER

    async def test_create_sets_default_value(self, svc: AssetService):
        asset = await svc.create(AssetCreate(name="Empty Asset"))
        assert asset.value == Decimal("0.00")

    async def test_create_preserves_all_fields(self, svc: AssetService):
        asset = await svc.create(
            AssetCreate(
                name="Family Car",
                type=AssetType.VEHICLE,
                value=Decimal("25000.00"),
                description="2021 Toyota Corolla",
                purchase_date=datetime.date(2021, 6, 15),
                purchase_price=Decimal("27000.00"),
            )
        )
        assert asset.name == "Family Car"
        assert asset.type == AssetType.VEHICLE
        assert asset.value == Decimal("25000.00")
        assert asset.description == "2021 Toyota Corolla"
        assert asset.purchase_date == datetime.date(2021, 6, 15)
        assert asset.purchase_price == Decimal("27000.00")

    async def test_create_real_estate_type(self, svc: AssetService):
        asset = await svc.create(AssetCreate(name="Apartment", type=AssetType.REAL_ESTATE))
        assert asset.type == AssetType.REAL_ESTATE

    async def test_create_valuables_type(self, svc: AssetService):
        asset = await svc.create(AssetCreate(name="Gold Ring", type=AssetType.VALUABLES))
        assert asset.type == AssetType.VALUABLES

    async def test_create_no_purchase_date_by_default(self, svc: AssetService):
        asset = await svc.create(AssetCreate(name="Tool"))
        assert asset.purchase_date is None

    async def test_create_no_purchase_price_by_default(self, svc: AssetService):
        asset = await svc.create(AssetCreate(name="Tool"))
        assert asset.purchase_price is None

    @pytest.mark.parametrize("payload", SQL_INJECTIONS)
    async def test_sql_injection_name_stored_verbatim(self, svc: AssetService, payload: str):
        """ORM parameterises queries — injection string is stored as plain text."""
        asset = await svc.create(AssetCreate(name=payload[:100]))
        fetched = await svc.get(asset.id)
        assert fetched is not None
        assert fetched.name == payload[:100]

    @pytest.mark.parametrize("payload", XSS_PAYLOADS)
    async def test_xss_name_stored_verbatim(self, svc: AssetService, payload: str):
        asset = await svc.create(AssetCreate(name=payload[:100]))
        fetched = await svc.get(asset.id)
        assert fetched is not None
        assert fetched.name == payload[:100]

    async def test_sql_injection_description_stored_verbatim(self, svc: AssetService):
        payload = "'; DROP TABLE assets; --"
        asset = await svc.create(AssetCreate(name="Test", description=payload))
        fetched = await svc.get(asset.id)
        assert fetched is not None
        assert fetched.description == payload


# ── Read ───────────────────────────────────────────────────────────────────────


class TestAssetServiceRead:
    async def test_get_nonexistent_returns_none(self, svc: AssetService):
        assert await svc.get(99999) is None

    async def test_get_returns_correct_asset(self, svc: AssetService):
        created = await svc.create(AssetCreate(name="Found It"))
        fetched = await svc.get(created.id)
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.name == "Found It"

    async def test_list_returns_empty_when_no_assets(self, svc: AssetService):
        assets = await svc.list()
        assert assets == []

    async def test_list_returns_all_assets(self, svc: AssetService):
        await svc.create(AssetCreate(name="Asset A"))
        await svc.create(AssetCreate(name="Asset B"))
        assets = await svc.list()
        assert len(assets) == 2

    async def test_list_ordered_by_name(self, svc: AssetService):
        await svc.create(AssetCreate(name="Zebra Asset"))
        await svc.create(AssetCreate(name="Alpha Asset"))
        await svc.create(AssetCreate(name="Mango Asset"))
        assets = await svc.list()
        names = [a.name for a in assets]
        assert names == sorted(names)

    async def test_list_single_asset(self, svc: AssetService):
        await svc.create(AssetCreate(name="Only One"))
        assets = await svc.list()
        assert len(assets) == 1
        assert assets[0].name == "Only One"


# ── Update ─────────────────────────────────────────────────────────────────────


class TestAssetServiceUpdate:
    async def test_update_name(self, svc: AssetService):
        asset = await svc.create(AssetCreate(name="Old Name"))
        updated = await svc.update(asset.id, AssetUpdate(name="New Name"))
        assert updated is not None
        assert updated.name == "New Name"

    async def test_update_value(self, svc: AssetService):
        asset = await svc.create(AssetCreate(name="Car", value=Decimal("20000.00")))
        updated = await svc.update(asset.id, AssetUpdate(value=Decimal("18000.00")))
        assert updated is not None
        assert updated.value == Decimal("18000.00")

    async def test_update_type(self, svc: AssetService):
        asset = await svc.create(AssetCreate(name="Plot", type=AssetType.OTHER))
        updated = await svc.update(asset.id, AssetUpdate(type=AssetType.REAL_ESTATE))
        assert updated is not None
        assert updated.type == AssetType.REAL_ESTATE

    async def test_update_nonexistent_returns_none(self, svc: AssetService):
        assert await svc.update(99999, AssetUpdate(name="x")) is None

    async def test_update_only_provided_fields(self, svc: AssetService):
        asset = await svc.create(
            AssetCreate(name="Test", type=AssetType.VEHICLE, value=Decimal("5000.00"))
        )
        updated = await svc.update(asset.id, AssetUpdate(name="Updated"))
        assert updated is not None
        assert updated.type == AssetType.VEHICLE  # unchanged
        assert updated.value == Decimal("5000.00")  # unchanged

    async def test_update_description(self, svc: AssetService):
        asset = await svc.create(AssetCreate(name="Ring", description="Plain"))
        updated = await svc.update(asset.id, AssetUpdate(description="Gold ring with diamond"))
        assert updated is not None
        assert updated.description == "Gold ring with diamond"

    async def test_update_purchase_date(self, svc: AssetService):
        asset = await svc.create(AssetCreate(name="House"))
        updated = await svc.update(asset.id, AssetUpdate(purchase_date=datetime.date(2020, 1, 10)))
        assert updated is not None
        assert updated.purchase_date == datetime.date(2020, 1, 10)

    async def test_update_persists_to_db(self, svc: AssetService):
        asset = await svc.create(AssetCreate(name="Before"))
        await svc.update(asset.id, AssetUpdate(name="After"))
        fetched = await svc.get(asset.id)
        assert fetched is not None
        assert fetched.name == "After"


# ── Delete ─────────────────────────────────────────────────────────────────────


class TestAssetServiceDelete:
    async def test_delete_existing(self, svc: AssetService):
        asset = await svc.create(AssetCreate(name="To Delete"))
        assert await svc.delete(asset.id) is True
        assert await svc.get(asset.id) is None

    async def test_delete_nonexistent_returns_false(self, svc: AssetService):
        assert await svc.delete(99999) is False

    async def test_delete_removes_from_list(self, svc: AssetService):
        a1 = await svc.create(AssetCreate(name="Keep"))
        a2 = await svc.create(AssetCreate(name="Remove"))
        await svc.delete(a2.id)
        remaining = await svc.list()
        assert len(remaining) == 1
        assert remaining[0].id == a1.id

    async def test_delete_same_id_twice_returns_false(self, svc: AssetService):
        asset = await svc.create(AssetCreate(name="Once"))
        assert await svc.delete(asset.id) is True
        assert await svc.delete(asset.id) is False


# ── NetWorthSummary physical_assets integration ────────────────────────────────


class TestNetWorthSummaryPhysicalAssets:
    """Tests that NetWorthService correctly loads assets and that
    NetWorthSummary.total_assets includes physical asset values."""

    async def test_physical_assets_empty_when_no_assets(self, session: AsyncSession):
        svc = NetWorthService(session)
        summary = await svc.get_summary()
        assert summary.physical_assets == []

    async def test_total_physical_assets_zero_when_no_assets(self, session: AsyncSession):
        svc = NetWorthService(session)
        summary = await svc.get_summary()
        assert summary.total_physical_assets == Decimal("0")

    async def test_total_assets_zero_with_no_accounts_or_physical_assets(
        self, session: AsyncSession
    ):
        svc = NetWorthService(session)
        summary = await svc.get_summary()
        assert summary.total_assets == Decimal("0")

    async def test_physical_assets_populated_after_create(self, session: AsyncSession):
        asset_svc = AssetService(session)
        await asset_svc.create(
            AssetCreate(name="House", type=AssetType.REAL_ESTATE, value=Decimal("300000.00"))
        )
        nw_svc = NetWorthService(session)
        summary = await nw_svc.get_summary()
        assert len(summary.physical_assets) == 1
        snap = summary.physical_assets[0]
        assert snap.name == "House"
        assert snap.type == "real_estate"
        assert snap.value == Decimal("300000.00")

    async def test_total_physical_assets_sums_values(self, session: AsyncSession):
        asset_svc = AssetService(session)
        await asset_svc.create(
            AssetCreate(name="House", type=AssetType.REAL_ESTATE, value=Decimal("300000.00"))
        )
        await asset_svc.create(
            AssetCreate(name="Car", type=AssetType.VEHICLE, value=Decimal("20000.00"))
        )
        nw_svc = NetWorthService(session)
        summary = await nw_svc.get_summary()
        assert summary.total_physical_assets == Decimal("320000.00")

    async def test_total_assets_includes_physical_asset_value(self, session: AsyncSession):
        asset_svc = AssetService(session)
        await asset_svc.create(
            AssetCreate(name="Apartment", type=AssetType.REAL_ESTATE, value=Decimal("150000.00"))
        )
        nw_svc = NetWorthService(session)
        summary = await nw_svc.get_summary()
        # No bank accounts — total_assets equals physical assets only
        assert summary.total_assets == Decimal("150000.00")

    async def test_physical_assets_sorted_by_name(self, session: AsyncSession):
        asset_svc = AssetService(session)
        await asset_svc.create(AssetCreate(name="Zebra", value=Decimal("1.00")))
        await asset_svc.create(AssetCreate(name="Alpha", value=Decimal("2.00")))
        nw_svc = NetWorthService(session)
        summary = await nw_svc.get_summary()
        names = [a.name for a in summary.physical_assets]
        assert names == sorted(names)

    async def test_physical_asset_snapshot_fields(self, session: AsyncSession):
        asset_svc = AssetService(session)
        asset = await asset_svc.create(
            AssetCreate(
                name="Gold Ring",
                type=AssetType.VALUABLES,
                value=Decimal("5000.00"),
                description="18k gold",
            )
        )
        nw_svc = NetWorthService(session)
        summary = await nw_svc.get_summary()
        snap = summary.physical_assets[0]
        assert snap.id == asset.id
        assert snap.name == "Gold Ring"
        assert snap.type == "valuables"
        assert snap.value == Decimal("5000.00")
        assert snap.description == "18k gold"


# ── PhysicalAssetSnapshot dataclass ───────────────────────────────────────────


class TestPhysicalAssetSnapshot:
    def test_snapshot_fields(self):
        snap = PhysicalAssetSnapshot(
            id=1,
            name="House",
            type="real_estate",
            value=Decimal("200000.00"),
            description="Main residence",
        )
        assert snap.id == 1
        assert snap.name == "House"
        assert snap.type == "real_estate"
        assert snap.value == Decimal("200000.00")
        assert snap.description == "Main residence"

    def test_snapshot_zero_value(self):
        snap = PhysicalAssetSnapshot(
            id=2, name="Empty", type="other", value=Decimal("0"), description=""
        )
        assert snap.value == Decimal("0")
