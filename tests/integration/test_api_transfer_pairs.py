# SPDX-License-Identifier: AGPL-3.0-or-later
"""``/api/v1/transfer-pairs``: suggest, accept and dismiss through the API.

The numbers are KAL-API-009's: 3123.86 PLN leaving "mKonto" on 2026-11-07 and
arriving on "Savings" on 2026-11-09.

Covers: KAL-API-009
"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from tests.integration.conftest import create_account, create_category, transaction_payload

SUGGEST = "/api/v1/transfer-pairs/suggestions"
PAIR = "/api/v1/transfer-pairs/"
DISMISS = "/api/v1/transfer-pairs/dismiss"
NOVEMBER = {"date_from": "2026-11-01", "date_to": "2026-11-30"}


class _Pair:
    """The scenario's two rows, plus an EUR account for the currency check."""

    def __init__(self, client: AsyncClient) -> None:
        self.client = client
        self.mkonto: dict[str, Any] = {}
        self.savings: dict[str, Any] = {}
        self.out_id = 0
        self.in_id = 0

    async def setup(self) -> _Pair:
        self.mkonto = await create_account(self.client, name="mKonto")
        self.savings = await create_account(self.client, name="Savings", type="savings")
        self.spend = (await create_category(self.client, name="Other"))["id"]
        self.earn = (await create_category(self.client, name="Inflow", type="income"))["id"]
        self.out_id = await self.row(self.mkonto["id"], "expense", "2026-11-07")
        self.in_id = await self.row(self.savings["id"], "income", "2026-11-09")
        return self

    async def row(self, account_id: int, tx_type: str, day: str, amount: str = "3123.86") -> int:
        category = self.spend if tx_type == "expense" else self.earn
        resp = await self.client.post(
            "/api/v1/transactions/",
            json=transaction_payload(account_id, category, type=tx_type, date=day, amount=amount),
        )
        assert resp.status_code == 201, resp.text
        return int(resp.json()["id"])

    async def get(self, tx_id: int) -> dict[str, Any]:
        resp = await self.client.get(f"/api/v1/transactions/{tx_id}")
        assert resp.status_code == 200
        return dict(resp.json())


async def _pair(client: AsyncClient) -> _Pair:
    return await _Pair(client).setup()


class TestSuggest:
    async def test_suggest_lists_the_scenario_pair(self, api_client: AsyncClient) -> None:
        p = await _pair(api_client)
        resp = await api_client.get(SUGGEST, params=NOVEMBER)
        assert resp.status_code == 200
        [pair] = resp.json()
        assert pair["amount"] == "3123.86"
        assert pair["currency"] == "PLN"
        assert pair["outgoing"] == {
            "id": p.out_id,
            "account_id": p.mkonto["id"],
            "date": "2026-11-07",
            "amount": "3123.86",
            "description": "test transaction",
        }
        assert pair["incoming"]["id"] == p.in_id
        assert pair["incoming"]["account_id"] == p.savings["id"]
        assert pair["incoming"]["date"] == "2026-11-09"

    async def test_suggest_requires_date_range(self, api_client: AsyncClient) -> None:
        assert (await api_client.get(SUGGEST)).status_code == 422
        resp = await api_client.get(SUGGEST, params={"date_from": "2026-11-01"})
        assert resp.status_code == 422
        resp = await api_client.get(SUGGEST, params={"date_to": "2026-11-30"})
        assert resp.status_code == 422

    async def test_suggest_span_capped(self, api_client: AsyncClient) -> None:
        # 2026-11-01 + 92 days = 2027-02-01: allowed; one day more is not.
        ok = await api_client.get(
            SUGGEST, params={"date_from": "2026-11-01", "date_to": "2027-02-01"}
        )
        assert ok.status_code == 200
        wide = await api_client.get(
            SUGGEST, params={"date_from": "2026-11-01", "date_to": "2027-02-02"}
        )
        assert wide.status_code == 422
        assert wide.json()["error"]["code"] == "validation_error"
        backwards = await api_client.get(
            SUGGEST, params={"date_from": "2026-11-30", "date_to": "2026-11-01"}
        )
        assert backwards.status_code == 422

    async def test_suggest_window_bounds(self, api_client: AsyncClient) -> None:
        await _pair(api_client)
        for bad in ({"max_days_apart": 0}, {"max_days_apart": 15}, {"amount_tolerance": -1}):
            resp = await api_client.get(SUGGEST, params={**NOVEMBER, **bad})
            assert resp.status_code == 422, bad
        # The legs are 2 days apart: a 1-day window finds nothing.
        narrow = await api_client.get(SUGGEST, params={**NOVEMBER, "max_days_apart": 1})
        assert narrow.json() == []


class TestAccept:
    async def test_accept_links_both_legs(self, api_client: AsyncClient) -> None:
        p = await _pair(api_client)
        resp = await api_client.post(PAIR, json={"transaction_ids": [p.out_id, p.in_id]})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["outgoing"]["id"] == p.out_id
        assert body["incoming"]["id"] == p.in_id
        out_leg, in_leg = await p.get(p.out_id), await p.get(p.in_id)
        for leg in (out_leg, in_leg):
            assert leg["type"] == "transfer"
            assert leg["category_id"] is None
            assert leg["is_internal_transfer"] is True
            assert leg["amount"] == "3123.86"
        assert out_leg["linked_transaction_id"] == p.in_id
        assert in_leg["linked_transaction_id"] == p.out_id
        assert out_leg["transfer_direction"] == "out"
        assert in_leg["transfer_direction"] == "in"
        assert (await api_client.get(SUGGEST, params=NOVEMBER)).json() == []

    async def test_accept_unordered_ids(self, api_client: AsyncClient) -> None:
        p = await _pair(api_client)
        resp = await api_client.post(PAIR, json={"transaction_ids": [p.in_id, p.out_id]})
        assert resp.status_code == 200
        assert resp.json()["outgoing"]["id"] == p.out_id
        assert resp.json()["incoming"]["id"] == p.in_id
        assert (await p.get(p.out_id))["transfer_direction"] == "out"

    async def test_accept_is_idempotent(self, api_client: AsyncClient) -> None:
        p = await _pair(api_client)
        first = await api_client.post(PAIR, json={"transaction_ids": [p.out_id, p.in_id]})
        assert first.status_code == 200
        before = await p.get(p.out_id), await p.get(p.in_id)
        for ids in ([p.out_id, p.in_id], [p.in_id, p.out_id]):
            again = await api_client.post(PAIR, json={"transaction_ids": ids})
            assert again.status_code == 200
            assert again.json()["outgoing"]["id"] == p.out_id
        after = await p.get(p.out_id), await p.get(p.in_id)
        assert after == before  # updated_at included: nothing was written

    async def test_accept_different_currency_422(self, api_client: AsyncClient) -> None:
        p = await _pair(api_client)
        wise = await create_account(api_client, name="Wise EUR", currency="EUR")
        eur_in = await p.row(wise["id"], "income", "2026-11-09")
        resp = await api_client.post(PAIR, json={"transaction_ids": [p.out_id, eur_in]})
        assert resp.status_code == 422
        assert (await p.get(p.out_id))["type"] == "expense"

    async def test_accept_already_linked_409(self, api_client: AsyncClient) -> None:
        p = await _pair(api_client)
        await api_client.post(PAIR, json={"transaction_ids": [p.out_id, p.in_id]})
        other_in = await p.row(p.savings["id"], "income", "2026-11-08")
        resp = await api_client.post(PAIR, json={"transaction_ids": [p.out_id, other_in]})
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "conflict"
        assert (await p.get(other_in))["linked_transaction_id"] is None

    async def test_accept_unknown_id_404(self, api_client: AsyncClient) -> None:
        p = await _pair(api_client)
        resp = await api_client.post(PAIR, json={"transaction_ids": [p.out_id, 999_999]})
        assert resp.status_code == 404

    async def test_accept_needs_exactly_two_ids(self, api_client: AsyncClient) -> None:
        p = await _pair(api_client)
        for ids in ([p.out_id], [p.out_id, p.in_id, p.in_id], [p.out_id, p.out_id]):
            resp = await api_client.post(PAIR, json={"transaction_ids": ids})
            assert resp.status_code == 422, ids


class TestDismiss:
    async def test_dismissed_pair_not_suggested(self, api_client: AsyncClient) -> None:
        p = await _pair(api_client)
        resp = await api_client.post(DISMISS, json={"transaction_ids": [p.in_id, p.out_id]})
        assert resp.status_code == 204
        again = await api_client.post(DISMISS, json={"transaction_ids": [p.out_id, p.in_id]})
        assert again.status_code == 204
        assert (await api_client.get(SUGGEST, params=NOVEMBER)).json() == []
        assert (await p.get(p.out_id))["type"] == "expense"

    async def test_dismiss_unknown_id_404(self, api_client: AsyncClient) -> None:
        p = await _pair(api_client)
        resp = await api_client.post(DISMISS, json={"transaction_ids": [p.out_id, 999_999]})
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "not_found"
