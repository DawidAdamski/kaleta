"""Unit tests for InstitutionService — uses in-memory SQLite."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.institution import InstitutionType
from kaleta.schemas.institution import InstitutionCreate, InstitutionUpdate
from kaleta.services import InstitutionService

SQL_INJECTION_NAMES = [
    "'; DROP TABLE institutions; --",
    "' OR '1'='1",
    "UNION SELECT * FROM institutions--",
    "admin'--",
]


@pytest.fixture
def svc(session: AsyncSession) -> InstitutionService:
    return InstitutionService(session)


class TestInstitutionServiceCreate:
    async def test_create_returns_institution_with_id(self, svc: InstitutionService):
        institution = await svc.create(InstitutionCreate(name="PKO Bank"))
        assert institution.id is not None
        assert institution.name == "PKO Bank"

    async def test_create_sets_default_type(self, svc: InstitutionService):
        institution = await svc.create(InstitutionCreate(name="Test Bank"))
        assert institution.type == InstitutionType.BANK

    async def test_create_preserves_all_fields(self, svc: InstitutionService):
        institution = await svc.create(
            InstitutionCreate(
                name="Revolut",
                type=InstitutionType.FINTECH,
                color="#FF5733",
                website="https://revolut.com",
                description="Digital bank.",
            )
        )
        assert institution.name == "Revolut"
        assert institution.type == InstitutionType.FINTECH
        assert institution.color == "#FF5733"
        assert institution.website == "https://revolut.com"
        assert institution.description == "Digital bank."

    async def test_create_with_nullable_fields_as_none(self, svc: InstitutionService):
        institution = await svc.create(InstitutionCreate(name="Minimal Bank"))
        assert institution.color is None
        assert institution.website is None
        assert institution.description is None

    async def test_create_all_institution_types(self, svc: InstitutionService):
        for i, institution_type in enumerate(InstitutionType):
            institution = await svc.create(
                InstitutionCreate(name=f"Institution {i}", type=institution_type)
            )
            assert institution.type == institution_type

    @pytest.mark.parametrize("payload", SQL_INJECTION_NAMES)
    async def test_sql_injection_name_stored_verbatim(self, svc: InstitutionService, payload: str):
        """ORM parameterises queries — injection string is stored as plain text."""
        institution = await svc.create(InstitutionCreate(name=payload[:100]))
        fetched = await svc.get(institution.id)
        assert fetched is not None
        assert fetched.name == payload[:100]

    async def test_xss_name_stored_verbatim(self, svc: InstitutionService):
        payload = "<script>alert('xss')</script>"
        institution = await svc.create(InstitutionCreate(name=payload[:100]))
        fetched = await svc.get(institution.id)
        assert fetched is not None
        assert fetched.name == payload[:100]

    async def test_xss_description_stored_verbatim(self, svc: InstitutionService):
        payload = '"><img src=x onerror=alert(1)>'
        institution = await svc.create(InstitutionCreate(name="Test", description=payload[:500]))
        fetched = await svc.get(institution.id)
        assert fetched is not None
        assert fetched.description == payload[:500]


class TestInstitutionServiceRead:
    async def test_get_nonexistent_returns_none(self, svc: InstitutionService):
        result = await svc.get(99999)
        assert result is None

    async def test_list_returns_all(self, svc: InstitutionService):
        await svc.create(InstitutionCreate(name="Alpha Bank"))
        await svc.create(InstitutionCreate(name="Beta Bank"))
        institutions = await svc.list()
        assert len(institutions) == 2

    async def test_list_ordered_by_name(self, svc: InstitutionService):
        await svc.create(InstitutionCreate(name="Zebra Finance"))
        await svc.create(InstitutionCreate(name="Alpha Bank"))
        institutions = await svc.list()
        assert institutions[0].name == "Alpha Bank"
        assert institutions[1].name == "Zebra Finance"

    async def test_list_empty_returns_empty_list(self, svc: InstitutionService):
        institutions = await svc.list()
        assert institutions == []

    async def test_get_with_accounts_nonexistent_returns_none(self, svc: InstitutionService):
        result = await svc.get_with_accounts(99999)
        assert result is None

    async def test_get_with_accounts_returns_institution(self, svc: InstitutionService):
        created = await svc.create(InstitutionCreate(name="Bank With Accounts"))
        result = await svc.get_with_accounts(created.id)
        assert result is not None
        assert result.id == created.id
        assert result.accounts == []


class TestInstitutionServiceUpdate:
    async def test_update_name(self, svc: InstitutionService):
        institution = await svc.create(InstitutionCreate(name="Old Name"))
        updated = await svc.update(institution.id, InstitutionUpdate(name="New Name"))
        assert updated is not None
        assert updated.name == "New Name"

    async def test_update_type(self, svc: InstitutionService):
        institution = await svc.create(InstitutionCreate(name="Test", type=InstitutionType.BANK))
        updated = await svc.update(institution.id, InstitutionUpdate(type=InstitutionType.BROKER))
        assert updated is not None
        assert updated.type == InstitutionType.BROKER

    async def test_update_optional_fields(self, svc: InstitutionService):
        institution = await svc.create(InstitutionCreate(name="Test Bank"))
        updated = await svc.update(
            institution.id,
            InstitutionUpdate(
                color="#123456",
                website="https://testbank.com",
                description="A test bank.",
            ),
        )
        assert updated is not None
        assert updated.color == "#123456"
        assert updated.website == "https://testbank.com"
        assert updated.description == "A test bank."

    async def test_update_nonexistent_returns_none(self, svc: InstitutionService):
        result = await svc.update(99999, InstitutionUpdate(name="x"))
        assert result is None

    async def test_update_only_provided_fields(self, svc: InstitutionService):
        institution = await svc.create(InstitutionCreate(name="Test", type=InstitutionType.FINTECH))
        updated = await svc.update(institution.id, InstitutionUpdate(name="New Name"))
        assert updated is not None
        assert updated.type == InstitutionType.FINTECH  # unchanged

    async def test_update_persists_to_db(self, svc: InstitutionService):
        institution = await svc.create(InstitutionCreate(name="Before"))
        await svc.update(institution.id, InstitutionUpdate(name="After"))
        fetched = await svc.get(institution.id)
        assert fetched is not None
        assert fetched.name == "After"


class TestInstitutionServiceDelete:
    async def test_delete_existing(self, svc: InstitutionService):
        institution = await svc.create(InstitutionCreate(name="To Delete"))
        result = await svc.delete(institution.id)
        assert result is True
        assert await svc.get(institution.id) is None

    async def test_delete_nonexistent_returns_false(self, svc: InstitutionService):
        result = await svc.delete(99999)
        assert result is False

    async def test_delete_does_not_affect_other_institutions(self, svc: InstitutionService):
        inst_a = await svc.create(InstitutionCreate(name="Keep Me"))
        inst_b = await svc.create(InstitutionCreate(name="Delete Me"))
        await svc.delete(inst_b.id)
        assert await svc.get(inst_a.id) is not None
        assert await svc.get(inst_b.id) is None
