# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for ImportRuleService — filename-pattern mapping memory.

Covers: KAL-CSV-014, KAL-CSV-015, KAL-CSV-016, KAL-CSV-017
"""

from __future__ import annotations

import logging
from dataclasses import fields
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import ValidationError
from kaleta.models.account import AccountType
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.import_rule import ImportRuleCreate, ImportRuleUpdate
from kaleta.services import AccountService, ImportRuleService
from kaleta.services.import_service import (
    ColumnMapping,
    QueueSettingsSnapshot,
    default_remember_mapping,
)


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

    def test_mbank_statement_name_keeps_account_digits(self) -> None:
        """mBank's <8 account digits>_<from>_<to>.csv keeps the account, drops the dates."""
        suggest = ImportRuleService.suggest_filename_pattern
        assert suggest("78886836_261011_261109.csv") == "78886836_*_*.csv"
        assert suggest("78886836_261011_261109.CSV") == "78886836_*_*.CSV"

    def test_wildcard_only_pattern_is_not_suggested(self) -> None:
        suggest = ImportRuleService.suggest_filename_pattern
        assert suggest("2025-10-01_2025-10-31.csv") == ""
        assert suggest("12345.csv") == ""
        assert suggest("") == ""

    def test_older_history_export_keeps_todays_behaviour(self) -> None:
        """The plan's decided case: not a statement name, first digit block only."""
        suggest = ImportRuleService.suggest_filename_pattern
        assert suggest("dawid72288564_000101_261013.csv") == "dawid*_000101_261013.csv"


class TestWildcardOnlyPatterns:
    async def test_create_refuses_wildcard_only_pattern(
        self, session: AsyncSession, account: object
    ) -> None:
        svc = ImportRuleService(session)
        for pattern in ("*_*_*.csv", "*.csv", "*", " *-* .csv"):
            with pytest.raises(ValidationError) as caught:
                await svc.create(
                    ImportRuleCreate(
                        filename_pattern=pattern,
                        account_id=account.id,  # type: ignore[attr-defined]
                        column_mapping={},
                    )
                )
            assert caught.value.message_key == "errors.import_rule.pattern_matches_everything"
        assert await svc.list() == []

    async def test_create_accepts_a_pattern_that_names_the_account(
        self, session: AsyncSession, account: object
    ) -> None:
        rule = await ImportRuleService(session).create(
            ImportRuleCreate(
                filename_pattern="78886836_*_*.csv",
                account_id=account.id,  # type: ignore[attr-defined]
                column_mapping={},
            )
        )
        assert rule.filename_pattern == "78886836_*_*.csv"

    async def test_create_log_has_no_pattern(
        self, session: AsyncSession, account: object, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Account digits in a pattern must not reach plain-text logs (ADR-35)."""
        caplog.set_level(logging.INFO, logger="kaleta.services.import_rule_service")
        rule = await ImportRuleService(session).create(
            ImportRuleCreate(
                filename_pattern="78886836_*_*.csv",
                account_id=account.id,  # type: ignore[attr-defined]
                column_mapping={},
            )
        )
        messages = [r.getMessage() for r in caplog.records]
        assert any(f"id={rule.id}" in m for m in messages)
        assert not any("78886836" in m for m in messages)


class TestDefaultRememberMapping:
    def test_default_remember_mapping_off_when_auto_matched(self) -> None:
        assert default_remember_mapping(auto_matched=True) is False
        assert default_remember_mapping(auto_matched=False) is True

    def test_default_remember_mapping_is_not_inherited_from_the_previous_file(self) -> None:
        """The queue snapshot carries no remember flag, so inheritance cannot copy one."""
        assert "remember_mapping" not in {f.name for f in fields(QueueSettingsSnapshot)}


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
