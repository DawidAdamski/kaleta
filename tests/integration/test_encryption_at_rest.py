# SPDX-License-Identifier: AGPL-3.0-or-later
"""Field-level encryption, seen from outside: the database holds ciphertext.

Runs with encryption on whatever the suite's mode, under the suite's
``TEST_DATA_KEY``: a bearer token rides on its member's unlock (the
``key_ring`` entry ``api_user`` puts there), and is refused with ``423`` once
that member is locked.

Covers: KAL-ENC-001, KAL-ENC-007, KAL-ENC-010
"""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Iterator

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.config import settings
from kaleta.crypto import key_ring, tenant_member_ref
from kaleta.db.types import TEXT_FORMAT_AES_GCM, exact_index, install_data_key_resolver
from kaleta.models.payee import Payee
from kaleta.models.user import User
from kaleta.services.backup_service import BackupService
from tests.conftest import SUITE_FAMILY, TEST_DATA_KEY, family_table, make_session_factory
from tests.integration.conftest import create_account, create_category, transaction_payload

SECRET = "Rent to Mr Kowalski, flat 7"


@pytest.fixture(autouse=True)
def _encrypted(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(settings, "encryption", "passphrase")
    install_data_key_resolver(lambda: TEST_DATA_KEY)
    yield
    install_data_key_resolver(None)
    key_ring.clear()


async def _raw_descriptions(db_engine) -> list[bytes]:  # type: ignore[no-untyped-def]
    factory = make_session_factory(db_engine)
    async with factory() as session:
        rows = await session.execute(
            text(f"SELECT description FROM {family_table('transactions')}")
        )
        return [bytes(value) for value in rows.scalars()]


async def test_the_database_holds_ciphertext_only(api_client: AsyncClient, db_engine) -> None:  # type: ignore[no-untyped-def]
    """Covers: KAL-ENC-001"""
    account = await create_account(api_client)
    category = await create_category(api_client)
    created = await api_client.post(
        "/api/v1/transactions/",
        json=transaction_payload(account["id"], category["id"], description=SECRET),
    )
    assert created.status_code == 201

    [stored] = await _raw_descriptions(db_engine)
    assert stored[0] == TEXT_FORMAT_AES_GCM
    assert SECRET.encode() not in stored
    assert b"Kowalski" not in stored

    listed = await api_client.get("/api/v1/transactions/")
    assert [item["description"] for item in listed.json()["items"]] == [SECRET]


async def test_a_locked_member_gets_423(api_client: AsyncClient, api_user: User) -> None:
    """Covers: KAL-ENC-007"""
    await create_account(api_client)

    key_ring.lock_member(tenant_member_ref(SUITE_FAMILY.tenant_id, api_user.id))

    for response in (
        await api_client.get("/api/v1/accounts/"),
        await api_client.post("/api/v1/payees/", json={"name": "Lidl"}),
    ):
        assert response.status_code == 423
        assert response.json()["error"]["code"] == "tenant_locked"


async def test_export_is_plaintext_and_restore_encrypts_again(session: AsyncSession) -> None:
    """Covers: KAL-ENC-010"""
    session.add(Payee(name="Biedronka"))
    await session.commit()

    archive = await BackupService(session).export()
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        payees = json.loads(zf.read("payees.json"))
    assert [row["name"] for row in payees] == ["Biedronka"]

    await BackupService(session).restore(archive)

    raw = (await session.execute(text(f"SELECT name FROM {family_table('payees')}"))).scalar_one()
    assert bytes(raw)[0] == TEXT_FORMAT_AES_GCM
    found = await session.execute(select(Payee).where(Payee.name_bidx == exact_index("Biedronka")))
    assert found.scalar_one().name == "Biedronka"
