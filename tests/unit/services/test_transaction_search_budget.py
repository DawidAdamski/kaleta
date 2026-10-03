# SPDX-License-Identifier: AGPL-3.0-or-later
"""Searching an encrypted ledger stays inside its budget (``hosted-field-encryption`` §4).

The description is ciphertext, so the search runs in Python over the
decrypted rows of the filtered period. The plan's acceptance: 50 000
transactions searched — the page *and* its count — within 300 ms. Best of
three runs, so a stray scheduler hiccup on a shared CI runner does not decide
it; the measured figures are in the plan's Implementation notes.

A performance gate, not a user scenario — the plan's acceptance criterion
names this file.
"""

from __future__ import annotations

import datetime
import time
from collections.abc import Iterator

import pytest
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.config import settings
from kaleta.db.types import install_data_key_resolver
from kaleta.models.account import Account
from kaleta.models.transaction import Transaction, TransactionType
from kaleta.services.transaction_service import TransactionService
from tests.conftest import TEST_DATA_KEY

# Literals from the plan's acceptance criterion.
ROWS = 50_000
BUDGET_MS = 300
MATCHES = 500


@pytest.fixture(autouse=True)
def _encrypted(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(settings, "encryption", "passphrase")
    install_data_key_resolver(lambda: TEST_DATA_KEY)
    yield
    install_data_key_resolver(None)


async def test_searching_50000_encrypted_transactions_stays_in_budget(
    session: AsyncSession,
) -> None:
    account = Account(name="Konto")
    session.add(account)
    await session.commit()
    start = datetime.date(2020, 1, 1)
    await session.execute(
        insert(Transaction),
        [
            {
                "account_id": account.id,
                "amount": 1,
                "type": TransactionType.EXPENSE,
                "date": start + datetime.timedelta(days=i % 2000),
                "description": (
                    "BIEDRONKA 123 POZNAN" if i % (ROWS // MATCHES) == 0 else f"Sklep nr {i} Kraków"
                ),
                "is_internal_transfer": False,
            }
            for i in range(ROWS)
        ],
    )
    await session.commit()
    service = TransactionService(session)

    timings: list[float] = []
    for _ in range(3):
        began = time.perf_counter()
        page = await service.list(search="biedronka", limit=50)
        total = await service.count(search="biedronka")
        timings.append((time.perf_counter() - began) * 1000)

    assert len(page) == 50
    assert total == MATCHES
    assert min(timings) < BUDGET_MS, f"search took {min(timings):.0f} ms (best of 3)"
