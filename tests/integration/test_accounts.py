"""Integration tests for /api/v1/accounts."""

from __future__ import annotations

from httpx import AsyncClient

from tests.integration.conftest import ACCOUNT_PAYLOAD, create_account


class TestListAccounts:
    async def test_list_empty(self, api_client: AsyncClient):
        resp = await api_client.get("/api/v1/accounts/")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_returns_created_accounts(self, api_client: AsyncClient):
        created = await create_account(api_client)
        resp = await api_client.get("/api/v1/accounts/")
        assert resp.status_code == 200
        ids = [item["id"] for item in resp.json()]
        assert created["id"] in ids


class TestCreateAccount:
    async def test_create_returns_201_with_schema_fields(self, api_client: AsyncClient):
        """Covers: KAL-ACC-001"""
        resp = await api_client.post("/api/v1/accounts/", json=ACCOUNT_PAYLOAD)
        assert resp.status_code == 201
        body = resp.json()
        assert body["id"] is not None
        assert body["name"] == ACCOUNT_PAYLOAD["name"]
        assert body["type"] == ACCOUNT_PAYLOAD["type"]
        assert body["balance"] == ACCOUNT_PAYLOAD["balance"]
        assert body["currency"] == ACCOUNT_PAYLOAD["currency"]
        assert "created_at" in body
        assert "updated_at" in body

    async def test_create_missing_name_returns_422(self, api_client: AsyncClient):
        """Covers: KAL-ACC-004"""
        resp = await api_client.post(
            "/api/v1/accounts/", json={"type": "checking", "balance": "0.00"}
        )
        assert resp.status_code == 422


class TestGetAccount:
    async def test_get_by_id_returns_200(self, api_client: AsyncClient):
        created = await create_account(api_client)
        resp = await api_client.get(f"/api/v1/accounts/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]

    async def test_get_nonexistent_returns_404(self, api_client: AsyncClient):
        resp = await api_client.get("/api/v1/accounts/999")
        assert resp.status_code == 404
        assert resp.json()["error"]["message"] == "Account not found"

    async def test_get_invalid_id_returns_422(self, api_client: AsyncClient):
        resp = await api_client.get("/api/v1/accounts/not-an-id")
        assert resp.status_code == 422


class TestUpdateAccount:
    async def test_update_returns_200(self, api_client: AsyncClient):
        """Covers: KAL-ACC-002"""
        created = await create_account(api_client)
        resp = await api_client.put(
            f"/api/v1/accounts/{created['id']}", json={"name": "Updated Name"}
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Name"

    async def test_update_empty_name_returns_422(self, api_client: AsyncClient):
        created = await create_account(api_client)
        resp = await api_client.put(f"/api/v1/accounts/{created['id']}", json={"name": ""})
        assert resp.status_code == 422

    async def test_update_nonexistent_returns_404(self, api_client: AsyncClient):
        resp = await api_client.put("/api/v1/accounts/999", json={"name": "Ghost"})
        assert resp.status_code == 404
        assert resp.json()["error"]["message"] == "Account not found"


class TestDeleteAccount:
    async def test_delete_returns_204(self, api_client: AsyncClient):
        """Covers: KAL-ACC-003"""
        created = await create_account(api_client)
        resp = await api_client.delete(f"/api/v1/accounts/{created['id']}")
        assert resp.status_code == 204
        assert resp.content == b""

    async def test_delete_nonexistent_returns_404(self, api_client: AsyncClient):
        resp = await api_client.delete("/api/v1/accounts/999")
        assert resp.status_code == 404
        assert resp.json()["error"]["message"] == "Account not found"

    async def test_delete_invalid_id_returns_422(self, api_client: AsyncClient):
        resp = await api_client.delete("/api/v1/accounts/not-an-id")
        assert resp.status_code == 422
