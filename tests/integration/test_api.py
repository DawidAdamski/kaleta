"""Integration tests for the REST API — uses in-memory SQLite via ASGITransport."""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from kaleta.api import create_api_router
from kaleta.api.deps import get_session


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def api_client(db_engine):
    """AsyncClient wired to a fresh FastAPI app that uses the test DB engine."""
    app = FastAPI()
    app.include_router(create_api_router())

    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async def override_session():
        async with factory() as s:
            yield s

    app.dependency_overrides[get_session] = override_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------

ACCOUNT_PAYLOAD = {"name": "Main Checking", "type": "checking", "balance": "100.00", "currency": "PLN"}


class TestAccountsApi:

    async def test_list_empty(self, api_client: AsyncClient):
        resp = await api_client.get("/api/v1/accounts/")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_create_returns_201_with_id(self, api_client: AsyncClient):
        resp = await api_client.post("/api/v1/accounts/", json=ACCOUNT_PAYLOAD)
        assert resp.status_code == 201
        body = resp.json()
        assert body["id"] is not None
        assert body["name"] == ACCOUNT_PAYLOAD["name"]

    async def test_get_by_id(self, api_client: AsyncClient):
        created = (await api_client.post("/api/v1/accounts/", json=ACCOUNT_PAYLOAD)).json()
        resp = await api_client.get(f"/api/v1/accounts/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]

    async def test_update_name(self, api_client: AsyncClient):
        created = (await api_client.post("/api/v1/accounts/", json=ACCOUNT_PAYLOAD)).json()
        resp = await api_client.put(
            f"/api/v1/accounts/{created['id']}", json={"name": "Updated Name"}
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Name"

    async def test_delete_returns_204_and_subsequent_get_is_404(self, api_client: AsyncClient):
        created = (await api_client.post("/api/v1/accounts/", json=ACCOUNT_PAYLOAD)).json()
        del_resp = await api_client.delete(f"/api/v1/accounts/{created['id']}")
        assert del_resp.status_code == 204
        get_resp = await api_client.get(f"/api/v1/accounts/{created['id']}")
        assert get_resp.status_code == 404

    async def test_get_nonexistent_returns_404(self, api_client: AsyncClient):
        resp = await api_client.get("/api/v1/accounts/999")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Institutions
# ---------------------------------------------------------------------------

INSTITUTION_PAYLOAD = {"name": "Test Bank", "type": "bank"}


class TestInstitutionsApi:

    async def test_list_empty(self, api_client: AsyncClient):
        resp = await api_client.get("/api/v1/institutions/")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_create_returns_201(self, api_client: AsyncClient):
        resp = await api_client.post("/api/v1/institutions/", json=INSTITUTION_PAYLOAD)
        assert resp.status_code == 201
        body = resp.json()
        assert body["id"] is not None
        assert body["name"] == INSTITUTION_PAYLOAD["name"]

    async def test_get_by_id(self, api_client: AsyncClient):
        created = (await api_client.post("/api/v1/institutions/", json=INSTITUTION_PAYLOAD)).json()
        resp = await api_client.get(f"/api/v1/institutions/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]

    async def test_delete_returns_204(self, api_client: AsyncClient):
        created = (await api_client.post("/api/v1/institutions/", json=INSTITUTION_PAYLOAD)).json()
        resp = await api_client.delete(f"/api/v1/institutions/{created['id']}")
        assert resp.status_code == 204


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

CATEGORY_PAYLOAD = {"name": "Food", "type": "expense"}


class TestCategoriesApi:

    async def test_list_empty(self, api_client: AsyncClient):
        resp = await api_client.get("/api/v1/categories/")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_create_expense_category(self, api_client: AsyncClient):
        resp = await api_client.post("/api/v1/categories/", json=CATEGORY_PAYLOAD)
        assert resp.status_code == 201
        body = resp.json()
        assert body["id"] is not None
        assert body["name"] == CATEGORY_PAYLOAD["name"]
        assert body["type"] == "expense"

    async def test_filter_by_type(self, api_client: AsyncClient):
        await api_client.post("/api/v1/categories/", json={"name": "Salary", "type": "income"})
        await api_client.post("/api/v1/categories/", json=CATEGORY_PAYLOAD)

        resp = await api_client.get("/api/v1/categories/?type=expense")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["type"] == "expense"

    async def test_delete_returns_204(self, api_client: AsyncClient):
        created = (await api_client.post("/api/v1/categories/", json=CATEGORY_PAYLOAD)).json()
        resp = await api_client.delete(f"/api/v1/categories/{created['id']}")
        assert resp.status_code == 204


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------

class TestTransactionsApi:

    @pytest_asyncio.fixture
    async def account_id(self, api_client: AsyncClient) -> int:
        resp = await api_client.post("/api/v1/accounts/", json=ACCOUNT_PAYLOAD)
        return resp.json()["id"]

    @pytest_asyncio.fixture
    async def category_id(self, api_client: AsyncClient) -> int:
        resp = await api_client.post("/api/v1/categories/", json=CATEGORY_PAYLOAD)
        return resp.json()["id"]

    def _tx_payload(self, account_id: int, category_id: int) -> dict:
        return {
            "account_id": account_id,
            "category_id": category_id,
            "amount": "50.00",
            "type": "expense",
            "date": "2026-01-15",
            "description": "test transaction",
        }

    async def test_create_transaction(
        self, api_client: AsyncClient, account_id: int, category_id: int
    ):
        resp = await api_client.post(
            "/api/v1/transactions/", json=self._tx_payload(account_id, category_id)
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["id"] is not None
        assert body["account_id"] == account_id

    async def test_list_returns_paged_response(
        self, api_client: AsyncClient, account_id: int, category_id: int
    ):
        await api_client.post(
            "/api/v1/transactions/", json=self._tx_payload(account_id, category_id)
        )
        resp = await api_client.get("/api/v1/transactions/")
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body
        assert "page" in body
        assert "page_size" in body
        assert "pages" in body
        assert body["total"] >= 1

    async def test_filter_by_account(
        self, api_client: AsyncClient, account_id: int, category_id: int
    ):
        await api_client.post(
            "/api/v1/transactions/", json=self._tx_payload(account_id, category_id)
        )
        resp = await api_client.get(f"/api/v1/transactions/?account_ids={account_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] >= 1
        for item in body["items"]:
            assert item["account_id"] == account_id

    async def test_get_by_id(
        self, api_client: AsyncClient, account_id: int, category_id: int
    ):
        created = (
            await api_client.post(
                "/api/v1/transactions/", json=self._tx_payload(account_id, category_id)
            )
        ).json()
        resp = await api_client.get(f"/api/v1/transactions/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]

    async def test_delete_returns_204(
        self, api_client: AsyncClient, account_id: int, category_id: int
    ):
        created = (
            await api_client.post(
                "/api/v1/transactions/", json=self._tx_payload(account_id, category_id)
            )
        ).json()
        resp = await api_client.delete(f"/api/v1/transactions/{created['id']}")
        assert resp.status_code == 204
        get_resp = await api_client.get(f"/api/v1/transactions/{created['id']}")
        assert get_resp.status_code == 404


# ---------------------------------------------------------------------------
# Budgets
# ---------------------------------------------------------------------------

class TestBudgetsApi:

    @pytest_asyncio.fixture
    async def category_id(self, api_client: AsyncClient) -> int:
        resp = await api_client.post("/api/v1/categories/", json=CATEGORY_PAYLOAD)
        return resp.json()["id"]

    def _budget_payload(self, category_id: int) -> dict:
        return {
            "category_id": category_id,
            "amount": "500.00",
            "month": 1,
            "year": 2026,
        }

    async def test_create_budget(self, api_client: AsyncClient, category_id: int):
        resp = await api_client.post("/api/v1/budgets/", json=self._budget_payload(category_id))
        assert resp.status_code == 201
        body = resp.json()
        assert body["id"] is not None
        assert body["category_id"] == category_id

    async def test_list_returns_list(self, api_client: AsyncClient, category_id: int):
        await api_client.post("/api/v1/budgets/", json=self._budget_payload(category_id))
        resp = await api_client.get("/api/v1/budgets/")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
        assert len(resp.json()) >= 1

    async def test_filter_by_year_and_month(self, api_client: AsyncClient, category_id: int):
        await api_client.post("/api/v1/budgets/", json=self._budget_payload(category_id))
        resp = await api_client.get("/api/v1/budgets/?year=2026&month=1")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) >= 1
        for item in items:
            assert item["year"] == 2026
            assert item["month"] == 1

    async def test_update_amount(self, api_client: AsyncClient, category_id: int):
        created = (
            await api_client.post("/api/v1/budgets/", json=self._budget_payload(category_id))
        ).json()
        resp = await api_client.put(
            f"/api/v1/budgets/{created['id']}", json={"amount": "750.00"}
        )
        assert resp.status_code == 200
        assert resp.json()["amount"] == "750.00"

    async def test_delete_returns_204(self, api_client: AsyncClient, category_id: int):
        created = (
            await api_client.post("/api/v1/budgets/", json=self._budget_payload(category_id))
        ).json()
        resp = await api_client.delete(f"/api/v1/budgets/{created['id']}")
        assert resp.status_code == 204
        get_resp = await api_client.get(f"/api/v1/budgets/{created['id']}")
        assert get_resp.status_code == 404
