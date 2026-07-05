# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for settings-related service helpers."""

from __future__ import annotations

import datetime
import json

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.audit_log import AuditLog
from kaleta.schemas.currency_rate import CurrencyRateCreate
from kaleta.services.audit_service import AuditService
from kaleta.services.backup_service import BackupService
from kaleta.services.currency_rate_service import CurrencyRateService


class TestBackupService:
    def test_export_filename_has_zip_suffix(self) -> None:
        filename = BackupService.export_filename()
        assert filename.startswith("kaleta_backup_")
        assert filename.endswith(".zip")


class TestAuditService:
    def test_changed_field_names_for_update(self) -> None:
        entry = AuditLog(
            id=1,
            timestamp=datetime.datetime(2024, 1, 1, 12, 0, 0),
            operation="UPDATE",
            table_name="transactions",
            record_id=42,
            old_data=json.dumps({"amount": "10.00", "description": "Coffee"}),
            new_data=None,
            reverted=False,
        )
        assert AuditService.changed_field_names(entry) == ("amount", "description")

    def test_changed_field_names_for_non_update(self) -> None:
        entry = AuditLog(
            id=2,
            timestamp=datetime.datetime(2024, 1, 1, 12, 0, 0),
            operation="INSERT",
            table_name="accounts",
            record_id=1,
            old_data=None,
            new_data=None,
            reverted=False,
        )
        assert AuditService.changed_field_names(entry) == ()

    @pytest.mark.asyncio
    async def test_list_for_display(self, session: AsyncSession) -> None:
        session.add(
            AuditLog(
                timestamp=datetime.datetime(2024, 1, 1, 12, 0, 0),
                operation="DELETE",
                table_name="categories",
                record_id=7,
                old_data='{"name": "Food"}',
                new_data=None,
                reverted=False,
            )
        )
        await session.commit()

        entries = await AuditService(session).list_for_display(limit=10)
        assert len(entries) == 1
        assert entries[0].operation == "DELETE"
        assert entries[0].table_name == "categories"
        assert entries[0].record_id == 7
        assert entries[0].changed_fields == ()


class TestCurrencyRateService:
    def test_build_relevant_pairs_adds_missing_account_currencies(self) -> None:
        pairs = CurrencyRateService.build_relevant_pairs(
            "PLN",
            {"PLN", "EUR", "USD"},
            [("GBP", "PLN")],
        )
        assert ("GBP", "PLN") in pairs
        assert ("EUR", "PLN") in pairs
        assert ("USD", "PLN") in pairs

    def test_build_relevant_pairs_skips_default_currency(self) -> None:
        pairs = CurrencyRateService.build_relevant_pairs("PLN", {"PLN"}, [])
        assert pairs == []

    @pytest.mark.asyncio
    async def test_list_recent_for_pairs(self, session: AsyncSession) -> None:
        svc = CurrencyRateService(session)
        await svc.create(
            CurrencyRateCreate(
                date=datetime.date(2024, 1, 1),
                from_currency="EUR",
                to_currency="PLN",
                rate="4.30",
            )
        )
        await svc.create(
            CurrencyRateCreate(
                date=datetime.date(2024, 2, 1),
                from_currency="EUR",
                to_currency="PLN",
                rate="4.35",
            )
        )

        rows = await svc.list_recent_for_pairs([("EUR", "PLN")], per_pair=1)
        assert len(rows) == 1
        assert rows[0].date == datetime.date(2024, 2, 1)

    @pytest.mark.asyncio
    async def test_create_with_inverse(self, session: AsyncSession) -> None:
        svc = CurrencyRateService(session)
        await svc.create_with_inverse(
            CurrencyRateCreate(
                date=datetime.date(2024, 3, 1),
                from_currency="EUR",
                to_currency="PLN",
                rate="4.00",
            )
        )

        direct = await svc.list_for_pair("EUR", "PLN")
        inverse = await svc.list_for_pair("PLN", "EUR")
        assert len(direct) == 1
        assert len(inverse) == 1
        assert inverse[0].rate == pytest.approx(0.25)
