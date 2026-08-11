# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for ImportRuleService — filename-pattern mapping memory.

Covers: KAL-CSV-014, KAL-CSV-015, KAL-CSV-016, KAL-CSV-017
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.account import AccountType
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.import_rule import ImportRuleCreate, ImportRuleUpdate
from kaleta.services import AccountService, ImportRuleService
from kaleta.services.import_service import ColumnMapping


@pytest.fixture
async def account(session: AsyncSession):
    return await AccountService(session).create(
        AccountCreate(name="mBank PLN", type=AccountType.CHECKING, balance=Decimal("0.00"))
    )


@pytest.fixture
async def other_account(session: AsyncSession):
    return await AccountService(session).create(
        AccountCreate(name="PKO PLN", type=AccountType.CHECKING, balance=Decimal("0.00"))
    )


class TestSuggestFilenamePattern:
    def test_digit_block_becomes_star(self) -> None:
        assert ImportRuleService.suggest_filename_pattern("mbank-2025-10.csv") == "mbank-*.csv"

    def test_no_digits_keeps_name(self) -> None:
        assert ImportRuleService.suggest_filename_pattern("statement.csv") == "statement.csv"

    def test_case_preserved_in_suggestion(self) -> None:
        assert ImportRuleService.suggest_filename_pattern("MBANK-2025-10.CSV") == "MBANK-*.CSV"


class TestImportRuleMatch:
    async def test_most_specific_prefix_wins(
        self, session: AsyncSession, account: object, other_account: object
    ) -> None:
        """Covers: KAL-CSV-016"""
        svc = ImportRuleService(session)
        await svc.create(
            ImportRuleCreate(
                filename_pattern="mbank-*.csv",
                account_id=account.id,  # type: ignore[attr-defined]
                column_mapping={"date": 0, "amount": 1, "description": 2},
            )
        )
        await svc.create(
            ImportRuleCreate(
                filename_pattern="mbank-2025-*.csv",
                account_id=other_account.id,  # type: ignore[attr-defined]
                column_mapping={"date": 0, "amount": 1, "description": 2},
            )
        )
        matched = await svc.match("mbank-2025-11.csv")
        assert matched is not None
        assert matched.filename_pattern == "mbank-2025-*.csv"
        assert matched.account_id == other_account.id  # type: ignore[attr-defined]

    async def test_tie_broken_by_last_used_at(
        self, session: AsyncSession, account: object, other_account: object
    ) -> None:
        """Covers: KAL-CSV-016"""
        svc = ImportRuleService(session)
        older = await svc.create(
            ImportRuleCreate(
                filename_pattern="bank-*.csv",
                account_id=account.id,  # type: ignore[attr-defined]
            )
        )
        newer = await svc.create(
            ImportRuleCreate(
                filename_pattern="BANK-*.CSV",
                account_id=other_account.id,  # type: ignore[attr-defined]
            )
        )
        # Same specificity (both "bank-" / "bank-" casefolded length before *).
        # Force last_used_at ordering.
        older.last_used_at = datetime.now(UTC) - timedelta(days=7)
        newer.last_used_at = datetime.now(UTC)
        await session.commit()

        matched = await svc.match("bank-2025-11.csv")
        assert matched is not None
        assert matched.id == newer.id

    async def test_case_insensitive_match(self, session: AsyncSession, account: object) -> None:
        svc = ImportRuleService(session)
        await svc.create(
            ImportRuleCreate(
                filename_pattern="mbank-*.csv",
                account_id=account.id,  # type: ignore[attr-defined]
            )
        )
        matched = await svc.match("MBANK-2025-11.CSV")
        assert matched is not None
        assert matched.filename_pattern == "mbank-*.csv"

    async def test_disabled_rules_skipped(self, session: AsyncSession, account: object) -> None:
        """Covers: KAL-CSV-017"""
        svc = ImportRuleService(session)
        rule = await svc.create(
            ImportRuleCreate(
                filename_pattern="mbank-*.csv",
                account_id=account.id,  # type: ignore[attr-defined]
            )
        )
        await svc.update(rule.id, ImportRuleUpdate(is_active=False))
        assert await svc.match("mbank-2025-12.csv") is None
        rules = await svc.list()
        assert len(rules) == 1
        assert rules[0].is_active is False

    async def test_delete_removes_permanently(self, session: AsyncSession, account: object) -> None:
        """Covers: KAL-CSV-017"""
        svc = ImportRuleService(session)
        rule = await svc.create(
            ImportRuleCreate(
                filename_pattern="mbank-*.csv",
                account_id=account.id,  # type: ignore[attr-defined]
            )
        )
        assert await svc.delete(rule.id) is True
        assert await svc.list() == []


class TestUpsertAndColumnMapping:
    async def test_upsert_from_import_creates_and_updates(
        self, session: AsyncSession, account: object, other_account: object
    ) -> None:
        """Covers: KAL-CSV-014"""
        svc = ImportRuleService(session)
        mapping = ColumnMapping(date=0, amount=1, description=2).to_dict()
        created = await svc.upsert_from_import(
            filename="mbank-2025-10.csv",
            filename_pattern=None,
            account_id=account.id,  # type: ignore[attr-defined]
            column_mapping=mapping,
        )
        assert created.filename_pattern == "mbank-*.csv"
        assert created.column_mapping["date"] == 0

        updated = await svc.upsert_from_import(
            filename="mbank-2025-11.csv",
            filename_pattern="mbank-*.csv",
            account_id=other_account.id,  # type: ignore[attr-defined]
            column_mapping={"date": 1, "amount": 2, "description": 3},
        )
        assert updated.id == created.id
        assert updated.account_id == other_account.id  # type: ignore[attr-defined]
        assert updated.column_mapping["date"] == 1

    def test_column_mapping_roundtrip(self) -> None:
        original = ColumnMapping(
            date=0,
            amount=2,
            description=1,
            payee=3,
            date_format="%Y-%m-%d",
            decimal_separator=",",
            amounts_negative_for_expenses=False,
        )
        restored = ColumnMapping.from_dict(original.to_dict())
        assert restored == original
