# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration tests for /api/v1/transactions."""

from __future__ import annotations

import datetime
from decimal import Decimal

from httpx import AsyncClient

from kaleta.services.budget_service import BudgetService
from kaleta.services.saved_report_service import ReportConfig, SavedReportService
from tests.conftest import make_session_factory
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
        """Covers: KAL-TXN-005"""
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
        """Covers: KAL-TXN-001, KAL-API-001"""
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
        assert resp.json()["error"]["message"] == "Transaction not found"

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
        resp = await api_client.put("/api/v1/transactions/999", json={"description": "ghost"})
        assert resp.status_code == 404
        assert resp.json()["error"]["message"] == "Transaction not found"

    async def test_create_unbalanced_split_returns_422(self, api_client: AsyncClient):
        """Covers: KAL-SPL-002"""
        account = await create_account(api_client)
        cat1 = await create_category(api_client, name="Groceries")
        cat2 = await create_category(api_client, name="Alcohol")
        resp = await api_client.post(
            "/api/v1/transactions/",
            json={
                "account_id": account["id"],
                "category_id": None,
                "amount": "214.50",
                "type": "expense",
                "date": "2025-06-01",
                "description": "Lidl split",
                "is_split": True,
                "splits": [
                    {"category_id": cat1["id"], "amount": "180.00", "note": ""},
                    {"category_id": cat2["id"], "amount": "20.00", "note": ""},
                ],
            },
        )
        assert resp.status_code == 422

    async def test_update_split_lines_returns_200(self, api_client: AsyncClient):
        """Covers: KAL-SPL-004"""
        account = await create_account(api_client)
        cat1 = await create_category(api_client, name="Groceries API")
        cat2 = await create_category(api_client, name="Alcohol API")
        created = (
            await api_client.post(
                "/api/v1/transactions/",
                json={
                    "account_id": account["id"],
                    "category_id": None,
                    "amount": "214.50",
                    "type": "expense",
                    "date": "2025-06-01",
                    "description": "Lidl split API",
                    "is_split": True,
                    "splits": [
                        {"category_id": cat1["id"], "amount": "180.00", "note": ""},
                        {"category_id": cat2["id"], "amount": "34.50", "note": ""},
                    ],
                },
            )
        ).json()
        resp = await api_client.put(
            f"/api/v1/transactions/{created['id']}",
            json={
                "splits": [
                    {"category_id": cat1["id"], "amount": "170.00", "note": ""},
                    {"category_id": cat2["id"], "amount": "44.50", "note": ""},
                ]
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        amounts = sorted(Decimal(s["amount"]) for s in body["splits"])
        assert amounts == [Decimal("44.50"), Decimal("170.00")]

    async def test_update_unbalanced_splits_returns_422(self, api_client: AsyncClient):
        """Covers: KAL-SPL-002"""
        account = await create_account(api_client)
        cat1 = await create_category(api_client, name="Groceries API 2")
        cat2 = await create_category(api_client, name="Alcohol API 2")
        created = (
            await api_client.post(
                "/api/v1/transactions/",
                json={
                    "account_id": account["id"],
                    "category_id": None,
                    "amount": "100.00",
                    "type": "expense",
                    "date": "2025-06-01",
                    "description": "Split API unbalanced",
                    "is_split": True,
                    "splits": [
                        {"category_id": cat1["id"], "amount": "60.00", "note": ""},
                        {"category_id": cat2["id"], "amount": "40.00", "note": ""},
                    ],
                },
            )
        ).json()
        resp = await api_client.put(
            f"/api/v1/transactions/{created['id']}",
            json={
                "splits": [
                    {"category_id": cat1["id"], "amount": "50.00", "note": ""},
                    {"category_id": cat2["id"], "amount": "40.00", "note": ""},
                ]
            },
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "validation_error"


class TestSplitAggregation:
    async def test_split_lines_feed_category_reports(self, api_client: AsyncClient, db_engine):
        """Covers: KAL-SPL-003"""
        account = await create_account(api_client)
        groceries = await create_category(api_client, name="Groceries")
        alcohol = await create_category(api_client, name="Alcohol")
        resp = await api_client.post(
            "/api/v1/transactions/",
            json={
                "account_id": account["id"],
                "category_id": None,
                "amount": "214.50",
                "type": "expense",
                "date": "2025-06-15",
                "description": "Lidl split",
                "is_split": True,
                "splits": [
                    {"category_id": groceries["id"], "amount": "180.00", "note": ""},
                    {"category_id": alcohol["id"], "amount": "34.50", "note": ""},
                ],
            },
        )
        assert resp.status_code == 201

        factory = make_session_factory(db_engine)
        async with factory() as session:
            budget_rows = await BudgetService(session).range_summary(
                datetime.date(2025, 6, 1),
                datetime.date(2025, 6, 30),
            )
            by_cat = {row.category_id: row.actual_amount for row in budget_rows}
            assert by_cat[groceries["id"]] == Decimal("180.00")
            assert by_cat[alcohol["id"]] == Decimal("34.50")

            report = await SavedReportService(session).execute(
                ReportConfig(
                    dimension="category",
                    metric="sum",
                    transaction_types=["expense"],
                    date_preset="custom",
                    date_from="2025-06-01",
                    date_to="2025-06-30",
                    category_ids=[alcohol["id"]],
                )
            )
            assert report.labels == ["Alcohol"]
            assert report.values == [34.5]


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
        assert resp.json()["error"]["message"] == "Transaction not found"

    async def test_delete_invalid_id_returns_422(self, api_client: AsyncClient):
        resp = await api_client.delete("/api/v1/transactions/not-an-id")
        assert resp.status_code == 422


class TestTransactionNotes:
    async def test_create_and_get_round_trip_notes(self, api_client: AsyncClient):
        """Covers: KAL-TXN-007"""
        account = await create_account(api_client)
        category = await create_category(api_client)
        payload = transaction_payload(
            account["id"], category["id"], notes="Bought for mum's birthday"
        )
        created = await api_client.post("/api/v1/transactions/", json=payload)
        assert created.status_code == 201
        assert created.json()["notes"] == "Bought for mum's birthday"

        fetched = await api_client.get(f"/api/v1/transactions/{created.json()['id']}")
        assert fetched.status_code == 200
        assert fetched.json()["notes"] == "Bought for mum's birthday"

    async def test_create_without_notes_returns_null(self, api_client: AsyncClient):
        account = await create_account(api_client)
        category = await create_category(api_client)
        resp = await api_client.post(
            "/api/v1/transactions/",
            json=transaction_payload(account["id"], category["id"]),
        )
        assert resp.status_code == 201
        assert resp.json()["notes"] is None

    async def test_create_with_blank_notes_returns_null(self, api_client: AsyncClient):
        account = await create_account(api_client)
        category = await create_category(api_client)
        resp = await api_client.post(
            "/api/v1/transactions/",
            json=transaction_payload(account["id"], category["id"], notes="   "),
        )
        assert resp.status_code == 201
        assert resp.json()["notes"] is None

    async def test_update_clears_notes(self, api_client: AsyncClient):
        """Covers: KAL-TXN-008"""
        account = await create_account(api_client)
        category = await create_category(api_client)
        created = (
            await api_client.post(
                "/api/v1/transactions/",
                json=transaction_payload(account["id"], category["id"], notes="Receipt #123"),
            )
        ).json()
        resp = await api_client.put(f"/api/v1/transactions/{created['id']}", json={"notes": None})
        assert resp.status_code == 200
        assert resp.json()["notes"] is None


class TestPutTransferLink:
    """``linked_transaction_id`` through PUT is a pairing: checked, and written on both legs.

    Covers: KAL-API-009
    """

    async def _legs(
        self, client: AsyncClient, *, in_currency: str = "PLN", in_amount: str = "3123.86"
    ) -> tuple[int, int]:
        self._n = getattr(self, "_n", 0) + 1
        n = self._n
        mkonto = await create_account(client, name=f"mKonto {n}")
        savings = await create_account(client, name=f"Savings {n}", currency=in_currency)
        spend = await create_category(client, name=f"Other {n}")
        earn = await create_category(client, name=f"Inflow {n}", type="income")
        out_resp = await client.post(
            "/api/v1/transactions/",
            json=transaction_payload(
                mkonto["id"], spend["id"], amount="3123.86", date="2026-11-07"
            ),
        )
        in_resp = await client.post(
            "/api/v1/transactions/",
            json=transaction_payload(
                savings["id"], earn["id"], type="income", amount=in_amount, date="2026-11-09"
            ),
        )
        return out_resp.json()["id"], in_resp.json()["id"]

    async def _get(self, client: AsyncClient, tx_id: int) -> dict:
        return (await client.get(f"/api/v1/transactions/{tx_id}")).json()

    async def test_put_link_writes_both_sides(self, api_client: AsyncClient):
        out_id, in_id = await self._legs(api_client)
        resp = await api_client.put(
            f"/api/v1/transactions/{out_id}", json={"linked_transaction_id": in_id}
        )
        assert resp.status_code == 200, resp.text
        out_leg, in_leg = await self._get(api_client, out_id), await self._get(api_client, in_id)
        assert out_leg["linked_transaction_id"] == in_id
        assert in_leg["linked_transaction_id"] == out_id
        for leg in (out_leg, in_leg):
            assert leg["type"] == "transfer"
            assert leg["category_id"] is None
            assert leg["is_internal_transfer"] is True
        assert (out_leg["transfer_direction"], in_leg["transfer_direction"]) == ("out", "in")

        # The second hand-written PUT of the 2026-11-09 fix, naming the same pair: still fine.
        again = await api_client.put(
            f"/api/v1/transactions/{in_id}",
            json={"linked_transaction_id": out_id, "type": "transfer", "transfer_direction": "in"},
        )
        assert again.status_code == 200
        assert (await self._get(api_client, out_id))["linked_transaction_id"] == in_id

    async def test_put_link_clear_clears_both_sides(self, api_client: AsyncClient):
        out_id, in_id = await self._legs(api_client)
        await api_client.put(
            f"/api/v1/transactions/{out_id}", json={"linked_transaction_id": in_id}
        )
        resp = await api_client.put(
            f"/api/v1/transactions/{in_id}", json={"linked_transaction_id": None}
        )
        assert resp.status_code == 200
        assert (await self._get(api_client, out_id))["linked_transaction_id"] is None
        assert (await self._get(api_client, in_id))["linked_transaction_id"] is None

    async def test_put_link_validates(self, api_client: AsyncClient):
        # Different currencies: 422, and neither row changes.
        out_id, eur_in = await self._legs(api_client, in_currency="EUR")
        resp = await api_client.put(
            f"/api/v1/transactions/{out_id}", json={"linked_transaction_id": eur_in}
        )
        assert resp.status_code == 422
        assert (await self._get(api_client, out_id))["linked_transaction_id"] is None
        assert (await self._get(api_client, eur_in))["linked_transaction_id"] is None

        # Different amounts: 422.
        out_id, short_in = await self._legs(api_client, in_amount="3000.00")
        resp = await api_client.put(
            f"/api/v1/transactions/{out_id}", json={"linked_transaction_id": short_in}
        )
        assert resp.status_code == 422

        # Unknown partner: 404. Itself: 422.
        resp = await api_client.put(
            f"/api/v1/transactions/{out_id}", json={"linked_transaction_id": 999_999}
        )
        assert resp.status_code == 404
        resp = await api_client.put(
            f"/api/v1/transactions/{out_id}", json={"linked_transaction_id": out_id}
        )
        assert resp.status_code == 422

        # A leg already linked elsewhere: 409.
        out_id, in_id = await self._legs(api_client)
        await api_client.put(
            f"/api/v1/transactions/{out_id}", json={"linked_transaction_id": in_id}
        )
        other_out, _ = await self._legs(api_client)
        resp = await api_client.put(
            f"/api/v1/transactions/{other_out}", json={"linked_transaction_id": in_id}
        )
        assert resp.status_code == 409
        assert (await self._get(api_client, in_id))["linked_transaction_id"] == out_id

    async def test_put_link_validates_two_outgoing_legs(self, api_client: AsyncClient):
        out_id, in_id = await self._legs(api_client)
        await api_client.put(
            f"/api/v1/transactions/{in_id}", json={"type": "transfer", "transfer_direction": "out"}
        )
        resp = await api_client.put(
            f"/api/v1/transactions/{out_id}",
            json={"type": "transfer", "transfer_direction": "out", "linked_transaction_id": in_id},
        )
        assert resp.status_code == 422
