# SPDX-License-Identifier: AGPL-3.0-or-later
"""The balance-sheet bar's proportions, over a real database.

Covers: KAL-INV-005 — the split is read off a summary the service built from
accounts and physical assets, not from a hand-made summary object, because
what the bar must agree with is the ledger.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.schemas.account import AccountCreate, AccountType
from kaleta.schemas.asset import AssetCreate, AssetType
from kaleta.services import AccountService, AssetService, NetWorthService
from kaleta.services.net_worth_service import balance_sheet_split


@pytest.mark.asyncio
async def test_balance_sheet_splits_into_held_owned_and_owed(session: AsyncSession) -> None:
    accounts = AccountService(session)
    await accounts.create(
        AccountCreate(
            name="Checking", type=AccountType.CHECKING, balance=Decimal("6000.00"), currency="PLN"
        )
    )
    await accounts.create(
        AccountCreate(
            name="Card", type=AccountType.CREDIT, balance=Decimal("-2000.00"), currency="PLN"
        )
    )
    await AssetService(session).create(
        AssetCreate(name="Car", type=AssetType.VEHICLE, value=Decimal("2000.00"), description="")
    )

    summary = await NetWorthService(session).get_summary(history_months=1)
    split = balance_sheet_split(summary)

    assert split is not None
    assert split.accounts == pytest.approx(60.0)
    assert split.physical == pytest.approx(20.0)
    assert split.liabilities == pytest.approx(20.0)
