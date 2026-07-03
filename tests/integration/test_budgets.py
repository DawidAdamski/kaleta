"""Integration tests for /api/v1/budgets."""

from __future__ import annotations

from httpx import AsyncClient

from tests.integration.conftest import budget_payload, create_category


class TestListBudgets:
    async def test_list_empty(self, api_client: AsyncClient):
        resp = await api_client.get("/api/v1/budgets/")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_filter_by_year_and_month(self, api_client: AsyncClient):
        category = await create_category(api_client)
        await api_client.post("/api/v1/budgets/", json=budget_payload(category["id"]))
        resp = await api_client.get("/api/v1/budgets/?year=2026&month=1")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) >= 1
        for item in items:
            assert item["year"] == 2026
            assert item["month"] == 1

    async def test_list_invalid_month_returns_422(self, api_client: AsyncClient):
        resp = await api_client.get("/api/v1/budgets/?month=13")
        assert resp.status_code == 422


class TestCreateBudget:
    async def test_create_returns_201_with_schema_fields(self, api_client: AsyncClient):
        category = await create_category(api_client)
        payload = budget_payload(category["id"])
        resp = await api_client.post("/api/v1/budgets/", json=payload)
        assert resp.status_code == 201
        body = resp.json()
        assert body["id"] is not None
        assert body["category_id"] == category["id"]
        assert body["amount"] == payload["amount"]
        assert body["month"] == payload["month"]
        assert body["year"] == payload["year"]
        assert "created_at" in body
        assert "updated_at" in body

    async def test_create_zero_amount_returns_422(self, api_client: AsyncClient):
        category = await create_category(api_client)
        resp = await api_client.post(
            "/api/v1/budgets/",
            json=budget_payload(category["id"], amount="0.00"),
        )
        assert resp.status_code == 422


class TestGetBudget:
    async def test_get_by_id_returns_200(self, api_client: AsyncClient):
        category = await create_category(api_client)
        created = (
            await api_client.post("/api/v1/budgets/", json=budget_payload(category["id"]))
        ).json()
        resp = await api_client.get(f"/api/v1/budgets/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]

    async def test_get_nonexistent_returns_404(self, api_client: AsyncClient):
        resp = await api_client.get("/api/v1/budgets/999")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Budget entry not found"

    async def test_get_invalid_id_returns_422(self, api_client: AsyncClient):
        resp = await api_client.get("/api/v1/budgets/not-an-id")
        assert resp.status_code == 422


class TestUpdateBudget:
    async def test_update_returns_200(self, api_client: AsyncClient):
        category = await create_category(api_client)
        created = (
            await api_client.post("/api/v1/budgets/", json=budget_payload(category["id"]))
        ).json()
        resp = await api_client.put(f"/api/v1/budgets/{created['id']}", json={"amount": "750.00"})
        assert resp.status_code == 200
        assert resp.json()["amount"] == "750.00"

    async def test_update_month_without_year_returns_422(self, api_client: AsyncClient):
        category = await create_category(api_client)
        created = (
            await api_client.post("/api/v1/budgets/", json=budget_payload(category["id"]))
        ).json()
        resp = await api_client.put(f"/api/v1/budgets/{created['id']}", json={"month": 2})
        assert resp.status_code == 422

    async def test_update_nonexistent_returns_404(self, api_client: AsyncClient):
        resp = await api_client.put("/api/v1/budgets/999", json={"amount": "100.00"})
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Budget entry not found"


class TestDeleteBudget:
    async def test_delete_returns_204(self, api_client: AsyncClient):
        category = await create_category(api_client)
        created = (
            await api_client.post("/api/v1/budgets/", json=budget_payload(category["id"]))
        ).json()
        resp = await api_client.delete(f"/api/v1/budgets/{created['id']}")
        assert resp.status_code == 204
        assert resp.content == b""

    async def test_delete_nonexistent_returns_404(self, api_client: AsyncClient):
        resp = await api_client.delete("/api/v1/budgets/999")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Budget entry not found"

    async def test_delete_invalid_id_returns_422(self, api_client: AsyncClient):
        resp = await api_client.delete("/api/v1/budgets/not-an-id")
        assert resp.status_code == 422
