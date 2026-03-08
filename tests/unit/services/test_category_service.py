"""Unit tests for CategoryService — uses in-memory SQLite."""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.category import CategoryType
from kaleta.schemas.category import CategoryCreate, CategoryUpdate
from kaleta.services import CategoryService


@pytest.fixture
def svc(session: AsyncSession) -> CategoryService:
    return CategoryService(session)


class TestCategoryServiceCreate:

    async def test_create_expense_category(self, svc: CategoryService):
        cat = await svc.create(CategoryCreate(name="Żywność", type=CategoryType.EXPENSE))
        assert cat.id is not None
        assert cat.name == "Żywność"
        assert cat.type == CategoryType.EXPENSE

    async def test_create_income_category(self, svc: CategoryService):
        cat = await svc.create(CategoryCreate(name="Wynagrodzenie", type=CategoryType.INCOME))
        assert cat.type == CategoryType.INCOME

    async def test_duplicate_name_raises(self, svc: CategoryService):
        await svc.create(CategoryCreate(name="Duplicate", type=CategoryType.EXPENSE))
        with pytest.raises(IntegrityError):
            await svc.create(CategoryCreate(name="Duplicate", type=CategoryType.INCOME))

    async def test_sql_injection_name_stored_verbatim(self, svc: CategoryService):
        payload = "'; DROP TABLE categories; --"[:100]
        cat = await svc.create(CategoryCreate(name=payload, type=CategoryType.EXPENSE))
        fetched = await svc.get(cat.id)
        assert fetched is not None
        assert fetched.name == payload

    async def test_xss_name_stored_verbatim(self, svc: CategoryService):
        payload = "<script>alert(1)</script>"[:100]
        cat = await svc.create(CategoryCreate(name=payload, type=CategoryType.EXPENSE))
        fetched = await svc.get(cat.id)
        assert fetched is not None
        assert fetched.name == payload


class TestCategoryServiceList:

    async def test_list_all(self, svc: CategoryService):
        await svc.create(CategoryCreate(name="Food", type=CategoryType.EXPENSE))
        await svc.create(CategoryCreate(name="Salary", type=CategoryType.INCOME))
        cats = await svc.list()
        assert len(cats) == 2

    async def test_list_filter_by_expense(self, svc: CategoryService):
        await svc.create(CategoryCreate(name="Food", type=CategoryType.EXPENSE))
        await svc.create(CategoryCreate(name="Salary", type=CategoryType.INCOME))
        expenses = await svc.list(type=CategoryType.EXPENSE)
        assert len(expenses) == 1
        assert expenses[0].name == "Food"

    async def test_list_filter_by_income(self, svc: CategoryService):
        await svc.create(CategoryCreate(name="Food", type=CategoryType.EXPENSE))
        await svc.create(CategoryCreate(name="Salary", type=CategoryType.INCOME))
        incomes = await svc.list(type=CategoryType.INCOME)
        assert len(incomes) == 1
        assert incomes[0].name == "Salary"

    async def test_list_empty(self, svc: CategoryService):
        cats = await svc.list()
        assert cats == []


class TestCategoryServiceUpdate:

    async def test_update_name(self, svc: CategoryService):
        cat = await svc.create(CategoryCreate(name="Old", type=CategoryType.EXPENSE))
        updated = await svc.update(cat.id, CategoryUpdate(name="New"))
        assert updated is not None
        assert updated.name == "New"
        assert updated.type == CategoryType.EXPENSE  # unchanged

    async def test_update_nonexistent_returns_none(self, svc: CategoryService):
        result = await svc.update(99999, CategoryUpdate(name="x"))
        assert result is None


class TestCategoryServiceDelete:

    async def test_delete_existing(self, svc: CategoryService):
        cat = await svc.create(CategoryCreate(name="ToDelete", type=CategoryType.EXPENSE))
        assert await svc.delete(cat.id) is True
        assert await svc.get(cat.id) is None

    async def test_delete_nonexistent(self, svc: CategoryService):
        assert await svc.delete(99999) is False
