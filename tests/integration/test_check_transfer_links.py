# SPDX-License-Identifier: AGPL-3.0-or-later
"""``scripts/check_transfer_links.py``: what it reports, from real API responses."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
from httpx import AsyncClient

from tests.integration.conftest import create_account

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_transfer_links.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_transfer_links", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # @dataclass resolves its module through sys.modules
    spec.loader.exec_module(module)
    return module


check = _load()


def _leg(account_id: int, direction: str, amount: str = "3123.86", **extra: Any) -> dict:
    return {
        "account_id": account_id,
        "amount": amount,
        "type": "transfer",
        "transfer_direction": direction,
        "is_internal_transfer": True,
        "date": "2026-11-07",
        "description": "Przelew własny",
        **extra,
    }


async def _post(client: AsyncClient, body: dict) -> int:
    resp = await client.post("/api/v1/transactions/", json=body)
    assert resp.status_code == 201, resp.text
    return int(resp.json()["id"])


async def _read(client: AsyncClient) -> tuple[list[dict], dict[int, dict | None], dict[int, str]]:
    """What ``run`` reads, fetched through the test client instead of a live URL."""
    resp = await client.get("/api/v1/transactions/", params={"type": "transfer", "page_size": 200})
    transfers = resp.json()["items"]
    linked = [r for r in transfers if r["linked_transaction_id"] is not None]
    by_id: dict[int, dict | None] = {r["id"]: r for r in transfers}
    for row in linked:
        pid = row["linked_transaction_id"]
        if pid not in by_id:
            got = await client.get(f"/api/v1/transactions/{pid}")
            by_id[pid] = got.json() if got.status_code == 200 else None
    accounts = (await client.get("/api/v1/accounts/")).json()
    return linked, by_id, {a["id"]: a["currency"] for a in accounts}


async def test_consistent_pair_reports_nothing(api_client: AsyncClient) -> None:
    mkonto = await create_account(api_client, name="mKonto")
    savings = await create_account(api_client, name="Savings")
    out_id = await _post(api_client, _leg(mkonto["id"], "out"))
    in_id = await _post(api_client, _leg(savings["id"], "in"))
    await api_client.post("/api/v1/transfer-pairs/", json={"transaction_ids": [out_id, in_id]})
    assert check.find_problems(*await _read(api_client)) == []


async def test_reports_one_sided_links(api_client: AsyncClient) -> None:
    """A row created with a link (POST does not check it) stands in for the old PUTs."""
    mkonto = await create_account(api_client, name="mKonto")
    savings = await create_account(api_client, name="Savings")
    lone_out = await _post(api_client, _leg(mkonto["id"], "out"))
    one_sided = await _post(api_client, _leg(savings["id"], "in", linked_transaction_id=lone_out))

    problems = check.find_problems(*await _read(api_client))
    assert [(p.kind, p.transaction_id, p.partner_id) for p in problems] == [
        ("one_sided", one_sided, lone_out)
    ]


def test_find_problems_flags_amount_currency_and_direction() -> None:
    linked = [
        {"id": 1, "linked_transaction_id": 2, "amount": "100.00", "account_id": 10,
         "transfer_direction": "out"},
        {"id": 2, "linked_transaction_id": 1, "amount": "90.00", "account_id": 20,
         "transfer_direction": "out"},
    ]  # fmt: skip
    partners = {1: linked[0], 2: linked[1]}
    problems = check.find_problems(linked, partners, {10: "PLN", 20: "EUR"})
    assert [p.kind for p in problems] == ["amount_mismatch", "currency_mismatch", "same_direction"]
    assert all(p.transaction_id == 1 for p in problems)  # the pair is reported once


def test_api_reader_pages_and_only_gets() -> None:
    seen: list[tuple[str, str]] = []
    page_of = {
        "1": {"items": [{"id": 1, "linked_transaction_id": 7}], "pages": 2},
        "2": {"items": [{"id": 2, "linked_transaction_id": None}], "pages": 2},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        if request.url.path == "/api/v1/transactions/":
            return httpx.Response(200, json=page_of[request.url.params["page"]])
        if request.url.path == "/api/v1/transactions/7":
            return httpx.Response(404, json={"error": {"code": "not_found", "message": ""}})
        return httpx.Response(200, content=json.dumps([{"id": 10, "currency": "PLN"}]))

    api = check._Api("http://kaleta.test", "token", 5.0)
    api.client = httpx.Client(base_url="http://kaleta.test", transport=httpx.MockTransport(handler))
    problems = check.run(api)
    assert [(p.kind, p.transaction_id, p.partner_id) for p in problems] == [("dangling", 1, 7)]
    assert {method for method, _ in seen} == {"GET"}
