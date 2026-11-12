# SPDX-License-Identifier: AGPL-3.0-or-later
"""``POST /api/v1/imports`` — a bank statement through the import pipeline.

Covers: KAL-API-008

The statement is a three-row mBank export written here; the expected
descriptions and categories are the literals of KAL-API-008.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, func, inspect, select
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from kaleta.config import settings
from kaleta.exceptions import ValidationError
from kaleta.models.account import Account, AccountType
from kaleta.models.category import Category, CategoryType
from kaleta.models.import_run import ImportRun
from kaleta.models.payee import Payee
from kaleta.models.transaction import Transaction
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.categorisation_rule import CategorisationRuleCreate
from kaleta.schemas.category import CategoryCreate
from kaleta.schemas.import_rule import ImportRuleCreate
from kaleta.services import AccountService, CategoryService
from kaleta.services.import_pipeline import ImportOptions, ImportPipeline
from kaleta.services.import_rule_service import ImportRuleService
from kaleta.services.import_service import ImportService, ParseQueuedFileResult
from kaleta.services.rule_service import RuleService
from tests.conftest import _POSTGRES_URL, SUITE_FAMILY

STATEMENT_NUMBER = "55114020040000330299990801"

_HEADER = [
    "#Numer rachunku",
    "55 1140 2004 0000 3302 9999 0801",
    "#Rodzaj rachunku",
    "EKONTO",
    "#Waluta",
    "PLN",
    "#Klient",
    "API Import Client",
    "#Za okres:",
    "2024-03-01;2024-03-31",
    (
        "#Data operacji;#Data księgowania;#Opis operacji;#Tytuł;#Nadawca/Odbiorca;"
        "#Numer rachunku;#Kwota"
    ),
]
_ROWS = [
    (
        "2024-03-04;2024-03-04;ZAKUP PRZY UŻYCIU KARTY;"
        "LIDL WARSZAWA DATA TRANSAKCJI: 2024-03-03;;;-45.00"
    ),
    (
        "2024-03-10;2024-03-10;PRZELEW PRZYCHODZĄCY;Wynagrodzenie 03/2024;"
        "ACME Sp. z o.o.;11 1020 1010 0000 0000 0000 1111;5000.00"
    ),
    (
        "2024-03-12;2024-03-12;PRZELEW WYCHODZĄCY;Czynsz marzec;"
        "Spółdzielnia Mieszkaniowa;22 1020 1010 0000 0000 0000 2222;-800.00"
    ),
]
MBANK_CSV = ("\n".join(_HEADER + _ROWS) + "\n").encode()

# KAL-API-008's literals: description → category name, in file order.
EXPECTED = [
    ("LIDL WARSZAWA", "Spożywcze"),
    ("ACME Sp. z o.o. — Wynagrodzenie 03/2024", "Wpływy"),
    ("Spółdzielnia Mieszkaniowa — Czynsz marzec", "Zakupy"),
]

URL = "/api/v1/imports/"


async def test_the_migration_adds_what_the_model_declares(db_engine: AsyncConnection) -> None:
    """The suite family is built by the real migrations: read ``import_runs`` back."""

    def _read(sync: Any) -> tuple[dict[str, bool], set[tuple[str, tuple[str, ...]]]]:
        found = inspect(sync)
        columns = {
            c["name"]: c["nullable"]
            for c in found.get_columns("import_runs", schema=SUITE_FAMILY.schema)
        }
        indexes = {
            (i["name"], tuple(i["column_names"]))
            for i in found.get_indexes("import_runs", schema=SUITE_FAMILY.schema)
        }
        return columns, indexes

    columns, indexes = await db_engine.run_sync(_read)
    assert columns == {c.name: c.nullable for c in ImportRun.__table__.columns}
    assert {
        ("ix_import_runs_idempotency_key", ("idempotency_key",)),
        ("ix_import_runs_file_hmac", ("file_hmac",)),
    } <= indexes


async def _setup(
    session: AsyncSession, *, account_name: str = "API Import Konto"
) -> dict[str, int]:
    account = await AccountService(session).create(
        AccountCreate(name=account_name, type=AccountType.CHECKING, currency="PLN")
    )
    categories = CategoryService(session)
    expense = await categories.create(CategoryCreate(name="Zakupy", type=CategoryType.EXPENSE))
    income = await categories.create(CategoryCreate(name="Wpływy", type=CategoryType.INCOME))
    groceries = await categories.create(CategoryCreate(name="Spożywcze", type=CategoryType.EXPENSE))
    await RuleService(session).create(
        CategorisationRuleCreate(pattern="LIDL", category_id=groceries.id)
    )
    await session.commit()
    return {"account": account.id, "expense": expense.id, "income": income.id}


def _params(ids: dict[str, int], **extra: Any) -> dict[str, Any]:
    params: dict[str, Any] = {
        "filename": "lista_operacji_202403.csv",
        "account_id": ids["account"],
        "default_expense_category_id": ids["expense"],
        "default_income_category_id": ids["income"],
    }
    params.update(extra)
    return params


async def _post(client: AsyncClient, body: bytes, params: dict[str, Any], **headers: str) -> Any:
    return await client.post(
        URL, content=body, params=params, headers={"Content-Type": "text/csv", **headers}
    )


async def _stored(session: AsyncSession, account_id: int) -> list[tuple[str, str]]:
    rows = (
        await session.execute(
            select(Transaction.description, Category.name)
            .join(Category, Category.id == Transaction.category_id)
            .where(Transaction.account_id == account_id)
            .order_by(Transaction.date)
        )
    ).all()
    return [(description, name) for description, name in rows]


async def _counts(session: AsyncSession) -> tuple[int, int, int]:
    tx = await session.scalar(select(func.count()).select_from(Transaction))
    runs = await session.scalar(select(func.count()).select_from(ImportRun))
    payees = await session.scalar(select(func.count()).select_from(Payee))
    return int(tx or 0), int(runs or 0), int(payees or 0)


async def test_import_mbank_statement_happy_path(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Covers: KAL-API-008"""
    ids = await _setup(session)
    resp = await _post(api_client, MBANK_CSV, _params(ids))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["imported_count"] == 3
    assert body["account_id"] == ids["account"]
    assert body["skipped"] == []
    assert body["transfer_window"] is not None
    assert await _stored(session, ids["account"]) == EXPECTED
    run = await session.get(ImportRun, body["import_run_id"])
    assert run is not None
    assert (run.filename, run.profile, run.imported_count) == (
        "lista_operacji_202403.csv",
        "mbank",
        3,
    )
    assert run.file_hmac == ImportPipeline.file_digest(MBANK_CSV)


async def test_dry_run_writes_nothing(api_client: AsyncClient, session: AsyncSession) -> None:
    """Covers: KAL-API-008"""
    ids = await _setup(session)
    before = await _counts(session)
    resp = await _post(api_client, MBANK_CSV, _params(ids, dry_run="true"))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [(r["description"], r["duplicate"]) for r in body["rows"]] == [
        (description, False) for description, _ in EXPECTED
    ]
    assert body["profile"] == "mbank"
    assert body["account_id"] == ids["account"]
    assert sorted(body["new_payee_names"]) == ["ACME Sp. z o.o.", "Spółdzielnia Mieszkaniowa"]
    assert await _counts(session) == before


async def test_same_file_twice_returns_409(api_client: AsyncClient, session: AsyncSession) -> None:
    """Covers: KAL-API-008"""
    ids = await _setup(session)
    first = await _post(api_client, MBANK_CSV, _params(ids))
    assert first.status_code == 201, first.text
    second = await _post(api_client, MBANK_CSV, _params(ids))
    assert second.status_code == 409
    error = second.json()["error"]
    assert error["code"] == "duplicate_file"
    assert f"import run {first.json()['import_run_id']}" in error["message"]
    # allow_reimport goes through; every row is a duplicate now and is skipped.
    again = await _post(api_client, MBANK_CSV, _params(ids, allow_reimport="true"))
    assert again.status_code == 201, again.text
    assert again.json()["imported_count"] == 0
    assert [s["reason"] for s in again.json()["skipped"]] == ["duplicate"] * 3
    assert len(await _stored(session, ids["account"])) == 3


async def test_idempotency_key_replays_result(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Covers: KAL-API-008"""
    ids = await _setup(session)
    key = {"Idempotency-Key": "statement-2024-03"}
    first = await _post(api_client, MBANK_CSV, _params(ids), **key)
    assert first.status_code == 201, first.text
    before = await _counts(session)
    replay = await _post(api_client, MBANK_CSV, _params(ids), **key)
    assert replay.status_code == 200, replay.text
    body = replay.json()
    assert body["replayed"] is True
    assert body["import_run_id"] == first.json()["import_run_id"]
    assert body["imported_count"] == 3
    assert await _counts(session) == before


async def test_unauthenticated_upload_rejected_before_body_read(
    api_client_unauth: AsyncClient,
) -> None:
    """Covers: KAL-API-008"""
    read: list[bytes] = []

    async def body() -> AsyncIterator[bytes]:
        read.append(MBANK_CSV)
        yield MBANK_CSV

    resp = await api_client_unauth.post(
        URL,
        content=body(),
        params={
            "filename": "x.csv",
            "default_expense_category_id": 1,
            "default_income_category_id": 2,
        },
    )
    assert resp.status_code == 401
    assert read == []


async def test_body_over_cap_413(
    api_client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Covers: KAL-API-008"""
    ids = await _setup(session)
    monkeypatch.setattr(settings, "max_upload_bytes", 100)
    before = await _counts(session)
    declared = await _post(api_client, MBANK_CSV, _params(ids))
    assert declared.status_code == 413
    assert declared.json()["error"]["code"] == "payload_too_large"

    # Without a Content-Length (chunked), the running count stops it instead.
    async def chunked() -> AsyncIterator[bytes]:
        for start in range(0, len(MBANK_CSV), 64):
            yield MBANK_CSV[start : start + 64]

    streamed = await api_client.post(URL, content=chunked(), params=_params(ids))
    assert streamed.status_code == 413
    assert await _counts(session) == before


async def test_rows_over_cap_413(
    api_client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Covers: KAL-API-008"""
    ids = await _setup(session)
    monkeypatch.setattr(settings, "api_import_max_rows", 2)
    resp = await _post(api_client, MBANK_CSV, _params(ids))
    assert resp.status_code == 413
    assert "3 rows" in resp.json()["error"]["message"]
    assert await _stored(session, ids["account"]) == []


async def test_no_account_422(api_client: AsyncClient, session: AsyncSession) -> None:
    """Covers: KAL-API-008

    No ``account_id``, no filename rule, and no account carries the number.
    """
    ids = await _setup(session)
    params = _params(ids)
    del params["account_id"]
    resp = await _post(api_client, MBANK_CSV, params)
    assert resp.status_code == 422
    assert resp.json()["error"]["message"] == "Select a target account."


async def test_ambiguous_number_409(api_client: AsyncClient, session: AsyncSession) -> None:
    """Covers: KAL-API-008"""
    ids = await _setup(session)
    accounts = AccountService(session)
    other = await accounts.create(
        AccountCreate(name="API Import Drugie", type=AccountType.CHECKING, currency="PLN")
    )
    await accounts.save_external_number(ids["account"], STATEMENT_NUMBER)
    await accounts.save_external_number(other.id, STATEMENT_NUMBER)
    params = _params(ids)
    del params["account_id"]
    resp = await _post(api_client, MBANK_CSV, params)
    assert resp.status_code == 409
    assert await _stored(session, ids["account"]) == []


#: A generic CSV whose headers no alias recognises: only a saved mapping reads it.
GENERIC_CSV = "Kiedy;Ile;Co\n2024-03-05;-12.50;Kawa Mokotów\n".encode()


async def test_generic_csv_without_a_mapping_422_lists_headers(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Covers: KAL-API-008"""
    ids = await _setup(session)
    resp = await _post(api_client, GENERIC_CSV, _params(ids, filename="kawiarnia_03.csv"))
    assert resp.status_code == 422
    error = resp.json()["error"]
    assert error["code"] == "import_needs_mapping"
    assert "Detected headers: Kiedy, Ile, Co." in error["message"]


async def test_generic_csv_uses_the_filename_rules_saved_mapping(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Covers: KAL-API-008

    No ``account_id``: the rule names the account as well as the columns.
    """
    ids = await _setup(session)
    await ImportRuleService(session).create(
        ImportRuleCreate(
            filename_pattern="kawiarnia_*",
            account_id=ids["account"],
            column_mapping={"date": 0, "amount": 1, "description": 2},
        )
    )
    await session.commit()
    params = _params(ids, filename="kawiarnia_03.csv")
    del params["account_id"]
    resp = await _post(api_client, GENERIC_CSV, params)
    assert resp.status_code == 201, resp.text
    assert resp.json()["account_id"] == ids["account"]
    assert await _stored(session, ids["account"]) == [("Kawa Mokotów", "Zakupy")]


async def test_a_header_only_csv_is_422(api_client: AsyncClient, session: AsyncSession) -> None:
    """Covers: KAL-API-008

    The headers map, but there is nothing under them: the page would send the
    reader to the mapping step, so the API names the headers it found.
    """
    ids = await _setup(session)
    resp = await _post(api_client, b"date;amount;description\n", _params(ids))
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "import_needs_mapping"
    assert await _stored(session, ids["account"]) == []


async def test_a_file_the_parser_refuses_is_422(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Covers: KAL-API-008

    A parse that fails outright (no mapping step to offer, e.g. a workbook
    without the XLSX extra) surfaces as ``import_unreadable`` with its key.
    """
    refused = ParseQueuedFileResult(profile="wise", error_key="import.xlsx_extra_missing")
    monkeypatch.setattr(ImportService, "parse_queued_file", lambda *_a, **_k: refused)
    with pytest.raises(ValidationError) as caught:
        await ImportPipeline(session).parse_upload(b"PK\x03\x04", "statement.xlsx")
    assert caught.value.code == "import_unreadable"
    assert caught.value.message_key == "import.xlsx_extra_missing"


# ── two requests at once, on two real connections ─────────────────────────────


def _independent_factory() -> tuple[async_sessionmaker[AsyncSession], Any]:
    """A session factory on its own engine: a separate connection that commits."""
    engine = create_async_engine(
        _POSTGRES_URL,
        poolclass=NullPool,
        execution_options={"schema_translate_map": {None: SUITE_FAMILY.schema}},
    )
    return async_sessionmaker(engine, expire_on_commit=False), engine


async def _purge(factory: async_sessionmaker[AsyncSession], ids: dict[str, int] | None) -> None:
    if ids is None:
        return
    async with factory() as s:
        await s.execute(delete(Transaction).where(Transaction.account_id == ids["account"]))
        await s.execute(delete(ImportRun).where(ImportRun.account_id == ids["account"]))
        await s.execute(delete(Account).where(Account.id == ids["account"]))
        for payee in (await s.execute(select(Payee))).scalars():
            if payee.name in ("ACME Sp. z o.o.", "Spółdzielnia Mieszkaniowa"):
                await s.delete(payee)
        for category in (await s.execute(select(Category))).scalars():
            if category.name in ("Zakupy", "Wpływy", "Spożywcze"):
                await s.delete(category)
        await s.commit()


@pytest_asyncio.fixture
async def racing_setup() -> AsyncIterator[tuple[dict[str, int], list[Any]]]:
    pairs = [_independent_factory() for _ in range(2)]
    factories = [f for f, _ in pairs]
    ids: dict[str, int] | None = None
    try:
        async with factories[0]() as s:
            ids = await _setup(s, account_name="API Import Wyścig")
        yield ids, factories
    finally:
        await _purge(factories[0], ids)
        for _, engine in pairs:
            await engine.dispose()


async def test_concurrent_imports_do_not_double_insert(
    racing_setup: tuple[dict[str, int], list[Any]],
) -> None:
    """Covers: KAL-API-008

    Both requests pass ``allow_reimport`` so neither is stopped by the file
    check: only the advisory lock keeps the second's duplicate check from
    running before the first has written.
    """
    ids, factories = racing_setup
    options = ImportOptions(
        filename="lista_operacji_202403.csv",
        account_id=ids["account"],
        expense_category_id=ids["expense"],
        income_category_id=ids["income"],
    )
    barrier = asyncio.Barrier(2)

    async def _one(factory: async_sessionmaker[AsyncSession]) -> int:
        async with factory() as session:
            await session.connection()
            await barrier.wait()
            outcome = await ImportPipeline(session).import_upload(
                MBANK_CSV, options, allow_reimport=True
            )
            return outcome.imported_count

    counts = await asyncio.gather(*(_one(f) for f in factories))
    assert sorted(counts) == [0, 3]
    async with factories[0]() as s:
        assert len(await _stored(s, ids["account"])) == 3
