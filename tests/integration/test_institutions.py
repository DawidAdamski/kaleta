"""Integration tests for /api/v1/institutions."""

from __future__ import annotations

from httpx import AsyncClient

from tests.integration.conftest import INSTITUTION_PAYLOAD, create_institution


class TestListInstitutions:
    async def test_list_empty(self, api_client: AsyncClient):
        resp = await api_client.get("/api/v1/institutions/")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_returns_created_institutions(self, api_client: AsyncClient):
        created = await create_institution(api_client)
        resp = await api_client.get("/api/v1/institutions/")
        assert resp.status_code == 200
        ids = [item["id"] for item in resp.json()]
        assert created["id"] in ids


class TestCreateInstitution:
    async def test_create_returns_201_with_schema_fields(self, api_client: AsyncClient):
        resp = await api_client.post("/api/v1/institutions/", json=INSTITUTION_PAYLOAD)
        assert resp.status_code == 201
        body = resp.json()
        assert body["id"] is not None
        assert body["name"] == INSTITUTION_PAYLOAD["name"]
        assert body["type"] == INSTITUTION_PAYLOAD["type"]
        assert "created_at" in body
        assert "updated_at" in body

    async def test_create_missing_name_returns_422(self, api_client: AsyncClient):
        resp = await api_client.post("/api/v1/institutions/", json={"type": "bank"})
        assert resp.status_code == 422


class TestGetInstitution:
    async def test_get_by_id_returns_200(self, api_client: AsyncClient):
        created = await create_institution(api_client)
        resp = await api_client.get(f"/api/v1/institutions/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]

    async def test_get_nonexistent_returns_404(self, api_client: AsyncClient):
        resp = await api_client.get("/api/v1/institutions/999")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Institution not found"

    async def test_get_invalid_id_returns_422(self, api_client: AsyncClient):
        resp = await api_client.get("/api/v1/institutions/not-an-id")
        assert resp.status_code == 422


class TestUpdateInstitution:
    async def test_update_returns_200(self, api_client: AsyncClient):
        created = await create_institution(api_client)
        resp = await api_client.put(
            f"/api/v1/institutions/{created['id']}", json={"name": "Updated Bank"}
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Bank"

    async def test_update_empty_name_returns_422(self, api_client: AsyncClient):
        created = await create_institution(api_client)
        resp = await api_client.put(f"/api/v1/institutions/{created['id']}", json={"name": ""})
        assert resp.status_code == 422

    async def test_update_nonexistent_returns_404(self, api_client: AsyncClient):
        resp = await api_client.put("/api/v1/institutions/999", json={"name": "Ghost"})
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Institution not found"


class TestDeleteInstitution:
    async def test_delete_returns_204(self, api_client: AsyncClient):
        created = await create_institution(api_client)
        resp = await api_client.delete(f"/api/v1/institutions/{created['id']}")
        assert resp.status_code == 204
        assert resp.content == b""

    async def test_delete_nonexistent_returns_404(self, api_client: AsyncClient):
        resp = await api_client.delete("/api/v1/institutions/999")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Institution not found"

    async def test_delete_invalid_id_returns_422(self, api_client: AsyncClient):
        resp = await api_client.delete("/api/v1/institutions/not-an-id")
        assert resp.status_code == 422
