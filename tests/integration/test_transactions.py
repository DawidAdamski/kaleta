"""Integration tests for /api/v1/transactions."""

from __future__ import annotations

from httpx import AsyncClient

from tests.integration.conftest import create_account, create_category, transaction_payload


class TestListTransactions:
    async def test_list_returns_paged_response(self, api_client: AsyncClient):
        account = await create_account(api_client)
        category = await create_category(api_client)
        await api_client.post(
            "/api/v1/transactions/",
            json=transaction_payload(account["id"], category["id"]),
        )
        resp = await api_client.get("/api/v1/transactions/")
        assert resp.status_code == 200
        body = resp.json()
        assert set(body.keys()) == {"items", "total", "page", "page_size", "pages"}
        assert body["total"] >= 1
        assert len(body["items"]) >= 1

    async def test_list_filter_by_account(self, api_client: AsyncClient):
        account = await create_account(api_client)
        category = await create_category(api_client)
        await api_client.post(
            "/api/v1/transactions/",
            json=transaction_payload(account["id"], category["id"]),
        )
        resp = await api_client.get(f"/api/v1/transactions/?account_ids={account['id']}")
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert item["account_id"] == account["id"]

    async def test_list_invalid_page_returns_422(self, api_client: AsyncClient):
        resp = await api_client.get("/api/v1/transactions/?page=0")
        assert resp.status_code == 422


class TestCreateTransaction:
    async def test_create_returns_201_with_schema_fields(self, api_client: AsyncClient):
        account = await create_account(api_client)
        category = await create_category(api_client)
        payload = transaction_payload(account["id"], category["id"])
        resp = await api_client.post("/api/v1/transactions/", json=payload)
        assert resp.status_code == 201
        body = resp.json()
        assert body["id"] is not None
        assert body["account_id"] == account["id"]
        assert body["category_id"] == category["id"]
        assert body["amount"] == payload["amount"]
        assert body["type"] == payload["type"]
        assert "created_at" in body
        assert "updated_at" in body

    async def test_create_expense_without_category_returns_422(self, api_client: AsyncClient):
        account = await create_account(api_client)
        payload = transaction_payload(account["id"], category_id=0)
        del payload["category_id"]
        resp = await api_client.post("/api/v1/transactions/", json=payload)
        assert resp.status_code == 422


class TestGetTransaction:
    async def test_get_by_id_returns_200(self, api_client: AsyncClient):
        account = await create_account(api_client)
        category = await create_category(api_client)
        created = (
            await api_client.post(
                "/api/v1/transactions/",
                json=transaction_payload(account["id"], category["id"]),
            )
        ).json()
        resp = await api_client.get(f"/api/v1/transactions/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]

    async def test_get_nonexistent_returns_404(self, api_client: AsyncClient):
        resp = await api_client.get("/api/v1/transactions/999")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Transaction not found"

    async def test_get_invalid_id_returns_422(self, api_client: AsyncClient):
        resp = await api_client.get("/api/v1/transactions/not-an-id")
        assert resp.status_code == 422


class TestUpdateTransaction:
    async def test_update_returns_200(self, api_client: AsyncClient):
        account = await create_account(api_client)
        category = await create_category(api_client)
        created = (
            await api_client.post(
                "/api/v1/transactions/",
                json=transaction_payload(account["id"], category["id"]),
            )
        ).json()
        resp = await api_client.put(
            f"/api/v1/transactions/{created['id']}",
            json={"description": "updated description"},
        )
        assert resp.status_code == 200
        assert resp.json()["description"] == "updated description"

    async def test_update_invalid_amount_returns_422(self, api_client: AsyncClient):
        account = await create_account(api_client)
        category = await create_category(api_client)
        created = (
            await api_client.post(
                "/api/v1/transactions/",
                json=transaction_payload(account["id"], category["id"]),
            )
        ).json()
        resp = await api_client.put(
            f"/api/v1/transactions/{created['id']}", json={"amount": "not-a-decimal"}
        )
        assert resp.status_code == 422

    async def test_update_nonexistent_returns_404(self, api_client: AsyncClient):
        resp = await api_client.put(
            "/api/v1/transactions/999", json={"description": "ghost"}
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Transaction not found"


class TestDeleteTransaction:
    async def test_delete_returns_204(self, api_client: AsyncClient):
        account = await create_account(api_client)
        category = await create_category(api_client)
        created = (
            await api_client.post(
                "/api/v1/transactions/",
                json=transaction_payload(account["id"], category["id"]),
            )
        ).json()
        resp = await api_client.delete(f"/api/v1/transactions/{created['id']}")
        assert resp.status_code == 204
        assert resp.content == b""

    async def test_delete_nonexistent_returns_404(self, api_client: AsyncClient):
        resp = await api_client.delete("/api/v1/transactions/999")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Transaction not found"

    async def test_delete_invalid_id_returns_422(self, api_client: AsyncClient):
        resp = await api_client.delete("/api/v1/transactions/not-an-id")
        assert resp.status_code == 422
