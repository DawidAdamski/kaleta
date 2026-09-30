# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ledger-derived balances end to end: the upgrade, the mBank import, the API.

Covers: KAL-ACC-005, KAL-ACC-007, KAL-ACC-009, KAL-ACC-010
"""

from __future__ import annotations

import asyncio
import datetime
import os
import sqlite3
from decimal import Decimal
from pathlib import Path

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from alembic import command
from kaleta.models.account import AccountType
from kaleta.schemas.account import AccountCreate
from kaleta.services import AccountService, TransactionService
from kaleta.services.import_service import ImportService, ParsedRow
from kaleta.services.setup_service import _alembic_config
from tests.integration.conftest import create_account, create_category, transaction_payload

# The revision before balances followed the ledger.
_PREVIOUS_HEAD = "3b168fa7bb71"


def _migrate(db_url: str, revision: str) -> None:
    os.environ["KALETA_MIGRATE_URL"] = db_url
    try:
        command.upgrade(_alembic_config(), revision)
    finally:
        os.environ.pop("KALETA_MIGRATE_URL", None)


def test_upgrading_keeps_every_balance_the_user_saw(tmp_path: Path) -> None:
    """Covers: KAL-ACC-009

    Runs on its own SQLite file whatever backend the suite uses, so it needs
    no backend guard: the pre-upgrade rows go in through ``sqlite3``.
    """
    db_path = tmp_path / "before.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    _migrate(db_url, _PREVIOUS_HEAD)

    with sqlite3.connect(db_path) as raw:
        raw.executemany(
            "INSERT INTO accounts (id, name, type, balance, currency) VALUES (?, ?, ?, ?, 'PLN')",
            [(1, "PKO Main", "CHECKING", "1234.56"), (2, "Oszczędności", "SAVINGS", "500.00")],
        )
        raw.executemany(
            "INSERT INTO transactions (id, account_id, amount, type, date, description, "
            "is_internal_transfer, is_split, linked_transaction_id) "
            "VALUES (?, ?, ?, ?, '2026-09-01', '', ?, 0, ?)",
            [
                (1, 1, "200.00", "EXPENSE", 0, None),
                (2, 1, "50.00", "INCOME", 0, None),
                # A linked pair saved the way create_transfer saves it.
                (3, 1, "300.00", "TRANSFER", 1, None),
                (4, 2, "300.00", "TRANSFER", 1, 3),
                # A lone leg from an old mBank import: its direction is lost.
                (5, 2, "100.00", "TRANSFER", 1, None),
            ],
        )
        raw.execute("UPDATE transactions SET linked_transaction_id = 4 WHERE id = 3")

    _migrate(db_url, "head")

    async def read_balances() -> dict[int, Decimal]:
        # Alembic's env.py runs its own event loop, so this test is sync and
        # opens one only for the read.
        engine = create_async_engine(db_url)
        try:
            async with AsyncSession(engine) as session:
                return await AccountService(session).balances()
        finally:
            await engine.dispose()

    balances = asyncio.run(read_balances())
    assert balances == {1: Decimal("1234.56"), 2: Decimal("500.00")}

    with sqlite3.connect(db_path) as raw:
        directions = dict(
            raw.execute("SELECT id, transfer_direction FROM transactions WHERE type = 'TRANSFER'")
        )
    assert directions == {3: "OUT", 4: "IN", 5: "OUT"}


async def test_an_imported_own_account_transfer_lowers_the_source_balance(
    session: AsyncSession,
) -> None:
    """Covers: KAL-ACC-010"""
    accounts = AccountService(session)
    pko = await accounts.create(
        AccountCreate(name="PKO Main", type=AccountType.CHECKING, balance=Decimal("1000.00"))
    )
    savings = await accounts.create(
        AccountCreate(name="Oszczędności", type=AccountType.SAVINGS, balance=Decimal("0.00"))
    )
    await accounts.save_external_number(savings.id, "55114020040000330278886836")

    row = ParsedRow(
        date=datetime.date(2026, 9, 15),
        amount=Decimal("-300.00"),
        description="Przelew własny",
        raw={
            "Numer rachunku": "55 1140 2004 0000 3302 7888 6836",
            "Nadawca/Odbiorca": "",
            "Opis operacji": "Przelew własny",
            "Tytuł": "",
        },
    )
    creates = await ImportService(session).to_transaction_creates_with_payees(
        [row], account_id=pko.id, known_account_digits={"55114020040000330278886836"}
    )
    await TransactionService(session).create_bulk(creates)

    assert await accounts.balance(pko.id) == Decimal("700.00")


class TestApiBalances:
    async def test_the_api_reports_the_derived_balance(self, api_client: AsyncClient) -> None:
        """Covers: KAL-ACC-005"""
        account = await create_account(api_client, name="PKO Main", balance="1000.00")
        food = await create_category(api_client, name="Jedzenie", type="expense")
        salary = await create_category(api_client, name="Pensja", type="income")
        for payload in (
            transaction_payload(account["id"], food["id"], amount="200.00"),
            transaction_payload(account["id"], salary["id"], amount="50.00", type="income"),
        ):
            assert (await api_client.post("/api/v1/transactions/", json=payload)).status_code == 201

        listed = await api_client.get("/api/v1/accounts/")
        assert [a["balance"] for a in listed.json()] == ["850.00"]
        got = await api_client.get(f"/api/v1/accounts/{account['id']}")
        assert got.json()["balance"] == "850.00"

    async def test_editing_or_deleting_moves_the_balance_back(
        self, api_client: AsyncClient
    ) -> None:
        """Covers: KAL-ACC-007"""
        account = await create_account(api_client, name="PKO Main", balance="1000.00")
        food = await create_category(api_client, name="Jedzenie", type="expense")
        created = await api_client.post(
            "/api/v1/transactions/",
            json=transaction_payload(account["id"], food["id"], amount="200.00"),
        )
        assert created.status_code == 201
        tx_id = created.json()["id"]

        edited = await api_client.put(f"/api/v1/transactions/{tx_id}", json={"amount": "150.00"})
        assert edited.status_code == 200
        got = await api_client.get(f"/api/v1/accounts/{account['id']}")
        assert got.json()["balance"] == "850.00"

        assert (await api_client.delete(f"/api/v1/transactions/{tx_id}")).status_code == 204
        got = await api_client.get(f"/api/v1/accounts/{account['id']}")
        assert got.json()["balance"] == "1000.00"

    async def test_put_balance_sets_the_current_balance(self, api_client: AsyncClient) -> None:
        account = await create_account(api_client, name="PKO Main", balance="1000.00")
        food = await create_category(api_client, name="Jedzenie", type="expense")
        payload = transaction_payload(account["id"], food["id"], amount="150.00")
        assert (await api_client.post("/api/v1/transactions/", json=payload)).status_code == 201

        resp = await api_client.put(f"/api/v1/accounts/{account['id']}", json={"balance": "900.00"})
        assert resp.status_code == 200
        assert resp.json()["balance"] == "900.00"

    async def test_a_transfer_without_direction_is_rejected(self, api_client: AsyncClient) -> None:
        account = await create_account(api_client, name="PKO Main")
        resp = await api_client.post(
            "/api/v1/transactions/",
            json={
                "account_id": account["id"],
                "amount": "10.00",
                "type": "transfer",
                "date": "2026-09-15",
            },
        )
        assert resp.status_code == 422
