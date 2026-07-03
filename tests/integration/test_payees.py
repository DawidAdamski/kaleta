"""Integration tests for /api/v1/payees."""

from __future__ import annotations

from httpx import AsyncClient

from tests.integration.conftest import PAYEE_PAYLOAD, create_payee


class TestListPayees:
    async def test_list_empty(self, api_client: AsyncClient):
        resp = await api_client.get("/api/v1/payees/")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_returns_created_payees(self, api_client: AsyncClient):
        created = await create_payee(api_client)
        resp = await api_client.get("/api/v1/payees/")
        assert resp.status_code == 200
        ids = [item["id"] for item in resp.json()]
        assert created["id"] in ids


class TestCreatePayee:
    async def test_create_returns_201_with_schema_fields(self, api_client: AsyncClient):
        resp = await api_client.post("/api/v1/payees/", json=PAYEE_PAYLOAD)
        assert resp.status_code == 201
        body = resp.json()
        assert body["id"] is not None
        assert body["name"] == PAYEE_PAYLOAD["name"]
        assert "created_at" in body
        assert "updated_at" in body

    async def test_create_missing_name_returns_422(self, api_client: AsyncClient):
        resp = await api_client.post("/api/v1/payees/", json={})
        assert resp.status_code == 422


class TestGetPayee:
    async def test_get_by_id_returns_200(self, api_client: AsyncClient):
        created = await create_payee(api_client)
        resp = await api_client.get(f"/api/v1/payees/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]

    async def test_get_nonexistent_returns_404(self, api_client: AsyncClient):
        resp = await api_client.get("/api/v1/payees/999")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Payee not found"

    async def test_get_invalid_id_returns_422(self, api_client: AsyncClient):
        resp = await api_client.get("/api/v1/payees/not-an-id")
        assert resp.status_code == 422


class TestUpdatePayee:
    async def test_update_returns_200(self, api_client: AsyncClient):
        created = await create_payee(api_client)
        resp = await api_client.put(
            f"/api/v1/payees/{created['id']}", json={"name": "Updated Payee"}
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Payee"

    async def test_update_empty_name_returns_422(self, api_client: AsyncClient):
        created = await create_payee(api_client)
        resp = await api_client.put(f"/api/v1/payees/{created['id']}", json={"name": ""})
        assert resp.status_code == 422

    async def test_update_nonexistent_returns_404(self, api_client: AsyncClient):
        resp = await api_client.put("/api/v1/payees/999", json={"name": "Ghost"})
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Payee not found"


class TestDeletePayee:
    async def test_delete_returns_204(self, api_client: AsyncClient):
        created = await create_payee(api_client)
        resp = await api_client.delete(f"/api/v1/payees/{created['id']}")
        assert resp.status_code == 204
        assert resp.content == b""

    async def test_delete_nonexistent_returns_404(self, api_client: AsyncClient):
        resp = await api_client.delete("/api/v1/payees/999")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Payee not found"

    async def test_delete_invalid_id_returns_422(self, api_client: AsyncClient):
        resp = await api_client.delete("/api/v1/payees/not-an-id")
        assert resp.status_code == 422


class TestMergePayees:
    async def test_merge_returns_deleted_count(self, api_client: AsyncClient):
        keep = await create_payee(api_client, name="Keep")
        merge_a = await create_payee(api_client, name="Merge A")
        merge_b = await create_payee(api_client, name="Merge B")
        resp = await api_client.post(
            "/api/v1/payees/merge",
            json={"keep_id": keep["id"], "merge_ids": [merge_a["id"], merge_b["id"]]},
        )
        assert resp.status_code == 200
        assert resp.json() == {"deleted": 2}
        list_resp = await api_client.get("/api/v1/payees/")
        names = {item["name"] for item in list_resp.json()}
        assert names == {"Keep"}

    async def test_merge_empty_merge_ids_returns_422(self, api_client: AsyncClient):
        keep = await create_payee(api_client)
        resp = await api_client.post(
            "/api/v1/payees/merge", json={"keep_id": keep["id"], "merge_ids": []}
        )
        assert resp.status_code == 422

    async def test_merge_nonexistent_keep_id_returns_404(self, api_client: AsyncClient):
        other = await create_payee(api_client, name="Other")
        resp = await api_client.post(
            "/api/v1/payees/merge", json={"keep_id": 999, "merge_ids": [other["id"]]}
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Payee not found"
