"""Integration tests for /api/v1/categories."""

from __future__ import annotations

from httpx import AsyncClient

from tests.integration.conftest import CATEGORY_PAYLOAD, create_category


class TestListCategories:
    async def test_list_empty(self, api_client: AsyncClient):
        resp = await api_client.get("/api/v1/categories/")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_filter_by_type(self, api_client: AsyncClient):
        await create_category(api_client, name="Salary", type="income")
        await create_category(api_client)
        resp = await api_client.get("/api/v1/categories/?type=expense")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["type"] == "expense"

    async def test_list_invalid_type_returns_422(self, api_client: AsyncClient):
        resp = await api_client.get("/api/v1/categories/?type=not-a-type")
        assert resp.status_code == 422


class TestCreateCategory:
    async def test_create_returns_201_with_schema_fields(self, api_client: AsyncClient):
        """Covers: KAL-CAT-001"""
        resp = await api_client.post("/api/v1/categories/", json=CATEGORY_PAYLOAD)
        assert resp.status_code == 201
        body = resp.json()
        assert body["id"] is not None
        assert body["name"] == CATEGORY_PAYLOAD["name"]
        assert body["type"] == CATEGORY_PAYLOAD["type"]
        assert body["children"] == []
        assert "created_at" in body
        assert "updated_at" in body

    async def test_create_missing_type_returns_422(self, api_client: AsyncClient):
        resp = await api_client.post("/api/v1/categories/", json={"name": "Food"})
        assert resp.status_code == 422


class TestGetCategory:
    async def test_get_by_id_returns_200(self, api_client: AsyncClient):
        created = await create_category(api_client)
        resp = await api_client.get(f"/api/v1/categories/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]

    async def test_get_nonexistent_returns_404(self, api_client: AsyncClient):
        resp = await api_client.get("/api/v1/categories/999")
        assert resp.status_code == 404
        assert resp.json()["error"]["message"] == "Category not found"

    async def test_get_invalid_id_returns_422(self, api_client: AsyncClient):
        resp = await api_client.get("/api/v1/categories/not-an-id")
        assert resp.status_code == 422


class TestUpdateCategory:
    async def test_update_returns_200(self, api_client: AsyncClient):
        """Covers: KAL-CAT-003"""
        created = await create_category(api_client)
        resp = await api_client.put(
            f"/api/v1/categories/{created['id']}", json={"name": "Groceries"}
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Groceries"

    async def test_update_empty_name_returns_422(self, api_client: AsyncClient):
        created = await create_category(api_client)
        resp = await api_client.put(f"/api/v1/categories/{created['id']}", json={"name": ""})
        assert resp.status_code == 422

    async def test_update_nonexistent_returns_404(self, api_client: AsyncClient):
        resp = await api_client.put("/api/v1/categories/999", json={"name": "Ghost"})
        assert resp.status_code == 404
        assert resp.json()["error"]["message"] == "Category not found"


class TestDeleteCategory:
    async def test_delete_returns_204(self, api_client: AsyncClient):
        """Covers: KAL-CAT-007"""
        created = await create_category(api_client)
        resp = await api_client.delete(f"/api/v1/categories/{created['id']}")
        assert resp.status_code == 204
        assert resp.content == b""

    async def test_delete_nonexistent_returns_404(self, api_client: AsyncClient):
        resp = await api_client.delete("/api/v1/categories/999")
        assert resp.status_code == 404
        assert resp.json()["error"]["message"] == "Category not found"

    async def test_delete_invalid_id_returns_422(self, api_client: AsyncClient):
        resp = await api_client.delete("/api/v1/categories/not-an-id")
        assert resp.status_code == 422
