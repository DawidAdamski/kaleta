# SPDX-License-Identifier: AGPL-3.0-or-later
"""``/api/v1/personal-loans`` — counterparties, loans, repayments, totals.

Covers: KAL-API-018

Names, amounts and dates are the literals of KAL-API-018.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from httpx import AsyncClient

from kaleta.api import create_api_router
from tests.integration.conftest import create_account, create_category

PL = "/api/v1/personal-loans"


async def _cp(client: AsyncClient, name: str) -> int:
    resp = await client.post(f"{PL}/counterparties", json={"name": name})
    assert resp.status_code == 201, resp.text
    cp_id: int = resp.json()["id"]
    return cp_id


async def _loan(
    client: AsyncClient, cp_id: int, principal: str, direction: str, opened: str
) -> dict[str, Any]:
    resp = await client.post(
        f"{PL}/",
        json={
            "counterparty_id": cp_id,
            "direction": direction,
            "principal": principal,
            "currency": "PLN",
            "opened_at": opened,
        },
    )
    assert resp.status_code == 201, resp.text
    body: dict[str, Any] = resp.json()
    return body


async def _world(client: AsyncClient) -> dict[str, int]:
    """mKonto with the 250.00 income of 2026-11-10."""
    account = (await create_account(client, name="mKonto", balance="0.00"))["id"]
    income_cat = (await create_category(client, name="Zwroty", type="income"))["id"]
    income = await client.post(
        "/api/v1/transactions/",
        json={
            "account_id": account,
            "category_id": income_cat,
            "amount": "250.00",
            "type": "income",
            "date": "2026-11-10",
            "description": "Marek oddaje",
        },
    )
    assert income.status_code == 201, income.text
    return {"account": account, "income": income.json()["id"]}


async def _ledger(client: AsyncClient, account: int) -> list[tuple[str, str, str]]:
    resp = await client.get("/api/v1/transactions/", params={"account_ids": account})
    return sorted((t["amount"], t["date"], t["description"]) for t in resp.json()["items"])


async def _repay(client: AsyncClient, loan_id: int, **body: Any) -> Any:
    return await client.post(f"{PL}/{loan_id}/repayments", json=body)


async def test_counterparty_create_get_update_and_duplicate_409(api_client: AsyncClient) -> None:
    """Covers: KAL-API-018"""
    marek = await _cp(api_client, "Marek Nowak")
    again = await api_client.post(f"{PL}/counterparties", json={"name": "Marek Nowak"})
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "counterparty_name_taken"
    got = await api_client.get(f"{PL}/counterparties/{marek}")
    assert got.json()["name"] == "Marek Nowak"
    anna = await _cp(api_client, "Anna Kowalska")
    clash = await api_client.put(f"{PL}/counterparties/{anna}", json={"name": "Marek Nowak"})
    assert clash.status_code == 409
    noted = await api_client.put(f"{PL}/counterparties/{anna}", json={"notes": "sąsiadka"})
    assert (noted.status_code, noted.json()["notes"]) == (200, "sąsiadka")
    names = [c["name"] for c in (await api_client.get(f"{PL}/counterparties")).json()]
    assert names == ["Anna Kowalska", "Marek Nowak"]
    assert (await api_client.get(f"{PL}/counterparties/999999")).status_code == 404


async def test_loan_lifecycle_link_mirror_overpay_settle(api_client: AsyncClient) -> None:
    """Covers: KAL-API-018"""
    w = await _world(api_client)
    loan = await _loan(
        api_client, await _cp(api_client, "Marek Nowak"), "400.00", "outgoing", "2026-11-01"
    )
    assert (loan["status"], loan["remaining"]) == ("outstanding", "400.00")

    linked = await _repay(
        api_client, loan["id"], amount="250.00", date="2026-11-10", link_transaction_id=w["income"]
    )
    assert linked.status_code == 201, linked.text
    got = (await api_client.get(f"{PL}/{loan['id']}")).json()
    assert (got["repaid_total"], got["remaining"], got["status"]) == (
        "250.00",
        "150.00",
        "outstanding",
    )

    mirrored = await _repay(
        api_client, loan["id"], amount="200.00", date="2026-11-20", link_account_id=w["account"]
    )
    assert mirrored.status_code == 201, mirrored.text
    assert ("200.00", "2026-11-20", "Personal loan repayment: Marek Nowak") in await _ledger(
        api_client, w["account"]
    )
    got = (await api_client.get(f"{PL}/{loan['id']}")).json()
    assert (got["status"], got["remaining"]) == ("settled", "-50.00")
    assert got["settled_at"] is not None


async def test_totals_by_direction(api_client: AsyncClient) -> None:
    """Covers: KAL-API-018"""
    w = await _world(api_client)
    marek = await _loan(
        api_client, await _cp(api_client, "Marek Nowak"), "400.00", "outgoing", "2026-11-01"
    )
    await _repay(
        api_client, marek["id"], amount="250.00", date="2026-11-10", link_transaction_id=w["income"]
    )
    await _repay(
        api_client, marek["id"], amount="200.00", date="2026-11-20", link_account_id=w["account"]
    )
    await _loan(
        api_client, await _cp(api_client, "Anna Kowalska"), "150.00", "incoming", "2026-11-05"
    )
    totals = (await api_client.get(f"{PL}/totals")).json()
    assert totals == {
        "they_owe_you": "0.00",
        "you_owe": "150.00",
        "outstanding_count": 1,
        "settled_count": 1,
    }


async def test_delete_repayment_reopens_loan_and_keeps_transaction(
    api_client: AsyncClient,
) -> None:
    """Covers: KAL-API-018"""
    w = await _world(api_client)
    loan = await _loan(
        api_client, await _cp(api_client, "Marek Nowak"), "400.00", "outgoing", "2026-11-01"
    )
    await _repay(
        api_client, loan["id"], amount="250.00", date="2026-11-10", link_transaction_id=w["income"]
    )
    mirror = await _repay(
        api_client, loan["id"], amount="200.00", date="2026-11-20", link_account_id=w["account"]
    )
    deleted = await api_client.delete(f"{PL}/{loan['id']}/repayments/{mirror.json()['id']}")
    assert deleted.status_code == 204
    got = (await api_client.get(f"{PL}/{loan['id']}")).json()
    assert (got["status"], got["remaining"], got["settled_at"]) == ("outstanding", "150.00", None)
    assert ("200.00", "2026-11-20", "Personal loan repayment: Marek Nowak") in await _ledger(
        api_client, w["account"]
    )


async def test_put_status_settled_stamps_settled_at(api_client: AsyncClient) -> None:
    """Covers: KAL-API-018"""
    anna = await _loan(
        api_client, await _cp(api_client, "Anna Kowalska"), "150.00", "incoming", "2026-11-05"
    )
    resp = await api_client.put(f"{PL}/{anna['id']}", json={"status": "settled"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "settled"
    assert resp.json()["settled_at"] is not None


async def test_same_transaction_linked_twice_is_409(api_client: AsyncClient) -> None:
    """Covers: KAL-API-018"""
    w = await _world(api_client)
    loan = await _loan(
        api_client, await _cp(api_client, "Marek Nowak"), "400.00", "outgoing", "2026-11-01"
    )
    first = await _repay(
        api_client, loan["id"], amount="250.00", date="2026-11-10", link_transaction_id=w["income"]
    )
    second = await _repay(
        api_client, loan["id"], amount="250.00", date="2026-11-10", link_transaction_id=w["income"]
    )
    assert [first.status_code, second.status_code] == [201, 409]
    assert second.json()["error"]["code"] == "loan_transaction_taken"


async def test_unknown_counterparty_and_unknown_account_are_422(api_client: AsyncClient) -> None:
    """Covers: KAL-API-018"""
    no_cp = await api_client.post(
        f"{PL}/",
        json={
            "counterparty_id": 999999,
            "direction": "outgoing",
            "principal": "400.00",
            "opened_at": "2026-11-01",
        },
    )
    assert no_cp.status_code == 422
    assert no_cp.json()["error"]["code"] == "unknown_counterparty"
    loan = await _loan(
        api_client, await _cp(api_client, "Marek Nowak"), "400.00", "outgoing", "2026-11-01"
    )
    no_acc = await _repay(
        api_client, loan["id"], amount="200.00", date="2026-11-20", link_account_id=999999
    )
    assert no_acc.status_code == 422
    assert no_acc.json()["error"]["code"] == "unknown_account"
    null = await api_client.put(f"{PL}/{loan['id']}", json={"principal": None})
    assert null.status_code == 422
    assert (await api_client.get(f"{PL}/{loan['id']}")).json()["repayments"] == []


async def test_null_name_unknown_category_and_unknown_new_counterparty_are_422(
    api_client: AsyncClient,
) -> None:
    """Covers: KAL-API-018"""
    w = await _world(api_client)
    marek = await _cp(api_client, "Marek Nowak")
    null_name = await api_client.put(f"{PL}/counterparties/{marek}", json={"name": None})
    assert null_name.status_code == 422
    assert null_name.json()["error"]["code"] == "null_field"
    loan = await _loan(api_client, marek, "400.00", "outgoing", "2026-11-01")
    no_cat = await _repay(
        api_client,
        loan["id"],
        amount="200.00",
        date="2026-11-20",
        link_account_id=w["account"],
        link_category_id=999999,
    )
    assert no_cat.status_code == 422
    assert no_cat.json()["error"]["code"] == "unknown_category"
    moved = await api_client.put(f"{PL}/{loan['id']}", json={"counterparty_id": 999999})
    assert moved.status_code == 422
    assert moved.json()["error"]["code"] == "unknown_counterparty"
    got = (await api_client.get(f"{PL}/{loan['id']}")).json()
    assert (got["counterparty_name"], got["repayments"]) == ("Marek Nowak", [])
    assert [a for a, _, _ in await _ledger(api_client, w["account"])] == ["250.00"]


async def test_ambiguous_repayment_link_is_422(api_client: AsyncClient) -> None:
    """Covers: KAL-API-018"""
    w = await _world(api_client)
    loan = await _loan(
        api_client, await _cp(api_client, "Marek Nowak"), "400.00", "outgoing", "2026-11-01"
    )
    resp = await _repay(
        api_client,
        loan["id"],
        amount="250.00",
        date="2026-11-10",
        link_transaction_id=w["income"],
        link_account_id=w["account"],
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "repayment_link_ambiguous"


async def test_repayment_of_another_loan_is_404(api_client: AsyncClient) -> None:
    """Covers: KAL-API-018"""
    cp = await _cp(api_client, "Marek Nowak")
    first = await _loan(api_client, cp, "400.00", "outgoing", "2026-11-01")
    other = await _loan(api_client, cp, "150.00", "outgoing", "2026-11-05")
    rep = await _repay(api_client, first["id"], amount="250.00", date="2026-11-10")
    wrong = await api_client.delete(f"{PL}/{other['id']}/repayments/{rep.json()['id']}")
    assert wrong.status_code == 404
    assert len((await api_client.get(f"{PL}/{first['id']}")).json()["repayments"]) == 1


async def test_delete_loan_keeps_linked_transactions(api_client: AsyncClient) -> None:
    """Covers: KAL-API-018"""
    w = await _world(api_client)
    loan = await _loan(
        api_client, await _cp(api_client, "Marek Nowak"), "400.00", "outgoing", "2026-11-01"
    )
    await _repay(
        api_client, loan["id"], amount="250.00", date="2026-11-10", link_transaction_id=w["income"]
    )
    await _repay(
        api_client, loan["id"], amount="200.00", date="2026-11-20", link_account_id=w["account"]
    )
    assert (await api_client.delete(f"{PL}/{loan['id']}")).status_code == 204
    assert (await api_client.get(f"{PL}/{loan['id']}")).status_code == 404
    assert [(a, d) for a, d, _ in await _ledger(api_client, w["account"])] == [
        ("200.00", "2026-11-20"),
        ("250.00", "2026-11-10"),
    ]


async def test_list_filters_by_status(api_client: AsyncClient) -> None:
    """Covers: KAL-API-018"""
    cp = await _cp(api_client, "Anna Kowalska")
    open_loan = await _loan(api_client, cp, "150.00", "incoming", "2026-11-05")
    closed = await _loan(api_client, cp, "100.00", "incoming", "2026-11-01")
    await api_client.put(f"{PL}/{closed['id']}", json={"status": "settled"})
    outstanding = (await api_client.get(f"{PL}/", params={"status": "outstanding"})).json()
    settled = (await api_client.get(f"{PL}/", params={"status": "settled"})).json()
    assert [loan["id"] for loan in outstanding] == [open_loan["id"]]
    assert [loan["id"] for loan in settled] == [closed["id"]]
    assert outstanding[0]["counterparty_name"] == "Anna Kowalska"


async def test_link_candidates_skip_linked_and_internal_transfers(api_client: AsyncClient) -> None:
    """Covers: KAL-API-018"""
    w = await _world(api_client)
    transfer = await api_client.post(
        "/api/v1/transactions/",
        json={
            "account_id": w["account"],
            "amount": "10.00",
            "type": "transfer",
            "transfer_direction": "out",
            "is_internal_transfer": True,
            "date": "2026-11-11",
        },
    )
    assert transfer.status_code == 201, transfer.text
    candidates_before = {c["id"] for c in (await api_client.get(f"{PL}/link-candidates")).json()}
    assert transfer.json()["id"] not in candidates_before
    assert w["income"] in candidates_before
    loan = await _loan(
        api_client, await _cp(api_client, "Marek Nowak"), "400.00", "outgoing", "2026-11-01"
    )
    await _repay(
        api_client, loan["id"], amount="250.00", date="2026-11-10", link_transaction_id=w["income"]
    )
    after = {c["id"] for c in (await api_client.get(f"{PL}/link-candidates")).json()}
    assert w["income"] not in after


def test_openapi_gives_every_personal_loan_operation_a_summary() -> None:
    """Covers: KAL-API-018"""
    app = FastAPI()
    app.include_router(create_api_router())
    ops = [
        op
        for path, item in app.openapi()["paths"].items()
        if path.startswith(PL)
        for op in item.values()
    ]
    assert len(ops) == 13
    assert all(op.get("summary") for op in ops)
