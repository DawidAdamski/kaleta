# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration tests for payee identities and automatic payee merging.

Expected values are the literals of the KAL-PID scenarios in docs/bdd.md.
"""

from __future__ import annotations

import datetime
import os
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from alembic import command
from kaleta.exceptions import ConflictError
from kaleta.models.account import AccountType
from kaleta.models.category import CategoryType
from kaleta.models.payee import Payee
from kaleta.models.transaction import Transaction, TransactionType
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.category import CategoryCreate
from kaleta.schemas.payee import PayeeCreate
from kaleta.schemas.payee_identity import PayeeIdentityCreate
from kaleta.schemas.transaction import TransactionCreate
from kaleta.services import (
    AccountService,
    CategoryService,
    DedupeService,
    PayeeService,
    TransactionService,
)
from kaleta.services.import_service import ImportService, ParsedRow
from kaleta.services.payee_merge_service import PayeeMergeService
from kaleta.services.setup_service import _alembic_config
from tests.conftest import _USE_POSTGRES
from tests.integration.conftest import create_account, create_category, transaction_payload

# ── Helpers ───────────────────────────────────────────────────────────────────


async def _payee(session: AsyncSession, name: str) -> int:
    return (await PayeeService(session).create(PayeeCreate(name=name))).id


async def _patterns(session: AsyncSession, payee_id: int) -> list[str]:
    return [i.pattern for i in await PayeeService(session).list_identities(payee_id)]


async def _payee_names(session: AsyncSession) -> list[str]:
    result = await session.execute(select(Payee.name).order_by(Payee.name))
    return list(result.scalars().all())


async def _account(session: AsyncSession) -> int:
    account = await AccountService(session).create(
        AccountCreate(name="Konto PID", type=AccountType.CHECKING)
    )
    return account.id


async def _category(session: AsyncSession) -> int:
    category = await CategoryService(session).create(
        CategoryCreate(name="Zakupy PID", type=CategoryType.EXPENSE)
    )
    return category.id


async def _expense(session: AsyncSession, account_id: int, category_id: int, payee_id: int) -> int:
    tx = await TransactionService(session).create(
        TransactionCreate(
            account_id=account_id,
            category_id=category_id,
            payee_id=payee_id,
            amount=Decimal("25.00"),
            type=TransactionType.EXPENSE,
            date=datetime.date(2026, 9, 1),
            description="Zakupy",
        )
    )
    return tx.id


def _mbank_row(counterparty: str) -> ParsedRow:
    return ParsedRow(
        date=datetime.date(2026, 9, 1),
        amount=Decimal("-19.99"),
        description="Zakupy",
        raw={
            "Numer rachunku": "",
            "Nadawca/Odbiorca": counterparty,
            "Opis operacji": "ZAKUP PRZY UŻYCIU KARTY",
            "Tytuł": "",
        },
    )


# ── Identities and matching ───────────────────────────────────────────────────


async def test_transaction_under_identity_spelling_attaches_to_payee(api_client: AsyncClient):
    """Covers: KAL-PID-005"""
    lidl = (await api_client.post("/api/v1/payees/", json={"name": "Lidl sp z o o"})).json()
    resp = await api_client.post(
        f"/api/v1/payees/{lidl['id']}/identities", json={"pattern": "LIDL POZNAN"}
    )
    assert resp.status_code == 201

    account = await create_account(api_client)
    category = await create_category(api_client)
    resp = await api_client.post(
        "/api/v1/transactions/",
        json=transaction_payload(account["id"], category["id"], payee_name="LIDL POZNAN"),
    )
    assert resp.status_code == 201
    assert resp.json()["payee_id"] == lidl["id"]

    names = [p["name"] for p in (await api_client.get("/api/v1/payees/")).json()]
    assert names == ["Lidl sp z o o"]


async def test_import_matches_identities_ignoring_case(session: AsyncSession):
    """Covers: KAL-PID-006"""
    lidl_id = await _payee(session, "Lidl sp z o o")
    await PayeeService(session).add_identity(lidl_id, PayeeIdentityCreate(pattern="LIDL POZNAN"))
    account_id = await _account(session)
    category_id = await _category(session)

    creates = await ImportService(session).to_transaction_creates_with_payees(
        [_mbank_row("Lidl Poznan"), _mbank_row("ROSSMANN 12")],
        account_id=account_id,
        default_expense_category_id=category_id,
    )

    assert creates[0].payee_id == lidl_id
    rossmann = await session.get(Payee, creates[1].payee_id)
    assert rossmann is not None
    assert rossmann.name == "ROSSMANN 12"
    assert await _payee_names(session) == ["Lidl sp z o o", "ROSSMANN 12"]


async def test_merge_consolidates_identities_into_keeper(session: AsyncSession):
    """Covers: KAL-PID-007"""
    svc = PayeeService(session)
    orlen_id = await _payee(session, "ORLEN SA")
    stacja_id = await _payee(session, "ORLEN STACJA 401")
    await svc.add_identity(stacja_id, PayeeIdentityCreate(pattern="PKN ORLEN 401"))

    await DedupeService(session).merge_payees(keeper_id=orlen_id, other_ids=[stacja_id])

    assert await _patterns(session, orlen_id) == ["ORLEN SA", "ORLEN STACJA 401", "PKN ORLEN 401"]
    matched = await svc.match_or_create_from_name("PKN ORLEN 401")
    assert matched.id == orlen_id
    assert await _payee_names(session) == ["ORLEN SA"]


async def test_payees_merge_api_also_consolidates_identities(api_client: AsyncClient):
    """Covers: KAL-PID-007"""
    orlen = (await api_client.post("/api/v1/payees/", json={"name": "ORLEN SA"})).json()
    stacja = (await api_client.post("/api/v1/payees/", json={"name": "ORLEN STACJA 401"})).json()
    await api_client.post(
        f"/api/v1/payees/{stacja['id']}/identities", json={"pattern": "PKN ORLEN 401"}
    )

    resp = await api_client.post(
        "/api/v1/payees/merge", json={"keep_id": orlen["id"], "merge_ids": [stacja["id"]]}
    )
    assert resp.status_code == 200

    identities = (await api_client.get(f"/api/v1/payees/{orlen['id']}/identities")).json()
    assert [i["pattern"] for i in identities] == [
        "ORLEN SA",
        "ORLEN STACJA 401",
        "PKN ORLEN 401",
    ]


async def test_spelling_belongs_to_one_payee_only(api_client: AsyncClient):
    """Covers: KAL-PID-013"""
    lidl = (await api_client.post("/api/v1/payees/", json={"name": "Lidl sp z o o"})).json()
    kaufland = (await api_client.post("/api/v1/payees/", json={"name": "Kaufland"})).json()
    await api_client.post(
        f"/api/v1/payees/{lidl['id']}/identities", json={"pattern": "LIDL POZNAN"}
    )

    resp = await api_client.post(
        f"/api/v1/payees/{kaufland['id']}/identities", json={"pattern": "lidl poznan"}
    )
    assert resp.status_code == 409
    assert "Lidl sp z o o" in resp.json()["error"]["message"]

    only = (await api_client.get(f"/api/v1/payees/{kaufland['id']}/identities")).json()
    assert [i["pattern"] for i in only] == ["Kaufland"]
    resp = await api_client.delete(f"/api/v1/payees/{kaufland['id']}/identities/{only[0]['id']}")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "last_identity"


# ── Backfill ──────────────────────────────────────────────────────────────────


@pytest.mark.skipif(_USE_POSTGRES, reason="Runs the migration chain on a SQLite file")
def test_upgrade_backfills_one_identity_per_payee(tmp_path: Path):
    """Covers: KAL-PID-009"""
    db_path = tmp_path / "backfill.db"
    os.environ["KALETA_MIGRATE_URL"] = f"sqlite+aiosqlite:///{db_path}"
    try:
        command.upgrade(_alembic_config(), "d5e6f7a8b9c0")
        with sqlite3.connect(db_path) as conn:
            conn.executemany(
                "INSERT INTO payees (name, created_at, updated_at) "
                "VALUES (?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                [("Biedronka",), ("ŻABKA  Poznań",)],
            )
        command.upgrade(_alembic_config(), "e6f7a8b9c0d1")
    finally:
        os.environ.pop("KALETA_MIGRATE_URL", None)

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT p.name, i.pattern, i.case_sensitive FROM payee_identities i "
            "JOIN payees p ON p.id = i.payee_id ORDER BY p.id, i.id"
        ).fetchall()
    assert rows == [("Biedronka", "Biedronka", 0), ("ŻABKA  Poznań", "ŻABKA Poznań", 0)]


# ── Merge proposals and automatic merge ──────────────────────────────────────


async def _seed_scan_pairs(session: AsyncSession) -> dict[str, int]:
    return {
        name: await _payee(session, name)
        for name in (
            "Rossmann Drogeria 12",
            "Rossmann Drogeria 13",
            "Decathlon Sport 1234",
            "Decathlon Sport 1987",
        )
    }


async def test_auto_merge_merges_confident_pairs_and_proposes_the_rest(session: AsyncSession):
    """Covers: KAL-PID-010"""
    ids = await _seed_scan_pairs(session)

    result = await PayeeMergeService(session).scan(auto_merge_threshold=0.92)

    assert [(m.merged_name, m.keeper_name, m.score) for m in result.merged] == [
        ("Rossmann Drogeria 13", "Rossmann Drogeria 12", 0.96)
    ]
    assert [(p.left_name, p.right_name, p.score) for p in result.proposals] == [
        ("Decathlon Sport 1234", "Decathlon Sport 1987", 0.88)
    ]
    assert await _payee_names(session) == [
        "Decathlon Sport 1234",
        "Decathlon Sport 1987",
        "Rossmann Drogeria 12",
    ]
    assert await _patterns(session, ids["Rossmann Drogeria 12"]) == [
        "Rossmann Drogeria 12",
        "Rossmann Drogeria 13",
    ]


async def test_scan_without_auto_merge_only_proposes(session: AsyncSession):
    """Covers: KAL-PID-010"""
    await _seed_scan_pairs(session)

    result = await PayeeMergeService(session).scan(auto_merge_threshold=None)

    assert result.merged == []
    assert [(p.left_name, p.right_name, p.score) for p in result.proposals] == [
        ("Rossmann Drogeria 12", "Rossmann Drogeria 13", 0.96),
        ("Decathlon Sport 1234", "Decathlon Sport 1987", 0.88),
    ]
    assert len(await _payee_names(session)) == 4


async def test_dismissed_proposal_is_not_proposed_again(api_client: AsyncClient):
    """Covers: KAL-PID-011"""
    for name in ("Decathlon Sport 1234", "Decathlon Sport 1987"):
        await api_client.post("/api/v1/payees/", json={"name": name})

    proposals = (await api_client.get("/api/v1/payees/merges/proposals")).json()
    assert [(p["left_name"], p["right_name"], p["score"]) for p in proposals] == [
        ("Decathlon Sport 1234", "Decathlon Sport 1987", 0.88)
    ]

    resp = await api_client.post(
        "/api/v1/payees/merges/proposals/dismiss",
        json={"left_id": proposals[0]["right_id"], "right_id": proposals[0]["left_id"]},
    )
    assert resp.status_code == 204

    assert (await api_client.get("/api/v1/payees/merges/proposals")).json() == []


async def test_undo_auto_merge_within_seven_days(session: AsyncSession):
    """Covers: KAL-PID-012"""
    ids = await _seed_scan_pairs(session)
    account_id = await _account(session)
    category_id = await _category(session)
    # Two rows keep "12" the keeper; "13" brings one row of its own.
    await _expense(session, account_id, category_id, ids["Rossmann Drogeria 12"])
    await _expense(session, account_id, category_id, ids["Rossmann Drogeria 12"])
    tx_id = await _expense(session, account_id, category_id, ids["Rossmann Drogeria 13"])
    merge_svc = PayeeMergeService(session)
    record = (await merge_svc.scan(auto_merge_threshold=0.92)).merged[0]
    assert (record.merged_name, record.keeper_name) == (
        "Rossmann Drogeria 13",
        "Rossmann Drogeria 12",
    )
    assert [e.merged_name for e in await merge_svc.recent_auto_merges()] == ["Rossmann Drogeria 13"]

    restored = await merge_svc.undo(record.id)

    assert restored.name == "Rossmann Drogeria 13"
    assert await _patterns(session, restored.id) == ["Rossmann Drogeria 13"]
    assert await _patterns(session, ids["Rossmann Drogeria 12"]) == ["Rossmann Drogeria 12"]
    tx = await session.get(Transaction, tx_id)
    assert tx is not None
    await session.refresh(tx)
    assert tx.payee_id == restored.id
    assert await merge_svc.recent_auto_merges() == []

    again = (await merge_svc.scan(auto_merge_threshold=0.92)).merged[0]
    eight_days_later = again.merged_at + datetime.timedelta(days=8)
    assert await merge_svc.recent_auto_merges(now=eight_days_later) == []
    with pytest.raises(ConflictError):
        await merge_svc.undo(again.id, now=eight_days_later)
