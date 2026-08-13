# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for BackupService — full-schema export/restore."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import Date, DateTime, Numeric, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.db.base import Base
from kaleta.exceptions import ValidationError
from kaleta.models import Payee
from kaleta.services.backup_service import (
    BackupService,
    _backup_tables,
    _current_alembic_revision,
    _deserialize_value,
)
from tests.backup_helpers import row_counts, seed_every_model, wipe_all


class TestBackupService:
    def test_export_filename_has_zip_suffix(self) -> None:
        filename = BackupService.export_filename()
        assert filename.startswith("kaleta_backup_")
        assert filename.endswith(".zip")

    def test_deserialize_value_coerces_json_scalars(self) -> None:
        assert _deserialize_value("2024-06-01", Date()) == date(2024, 6, 1)
        assert _deserialize_value("2024-06-01T12:00:00", DateTime()) == datetime(
            2024, 6, 1, 12, 0, 0
        )
        aware = _deserialize_value("2024-06-01T12:00:00+00:00", DateTime(timezone=True))
        assert aware == datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        naive = _deserialize_value("2024-06-01T12:00:00+00:00", DateTime())
        assert naive == datetime(2024, 6, 1, 12, 0, 0)
        assert _deserialize_value("42.50", Numeric(12, 2)) == Decimal("42.50")

    def test_backup_tables_matches_metadata(self) -> None:
        assert _backup_tables() == [t.name for t in Base.metadata.sorted_tables]
        # Sanity: previously missing domains must be present.
        names = set(_backup_tables())
        for required in (
            "payees",
            "tags",
            "transaction_tags",
            "subscriptions",
            "personal_loans",
            "users",
            "api_tokens",
            "audit_log",
            "institutions",
            "currency_rates",
            "import_runs",
        ):
            assert required in names

    @pytest.mark.asyncio
    async def test_export_stamps_alembic_revision(self, session: AsyncSession) -> None:
        data = await BackupService(session).export()
        with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
            meta = json.loads(zf.read("metadata.json"))
        assert meta["version"] == "1"
        assert meta["alembic_revision"] == _current_alembic_revision()
        assert set(meta["tables"]) == set(_backup_tables())

    @pytest.mark.asyncio
    async def test_round_trip_preserves_all_table_counts(self, session: AsyncSession) -> None:
        await seed_every_model(session)
        before = await row_counts(session)
        assert all(count >= 1 for count in before.values()), before

        data = await BackupService(session).export()
        await wipe_all(session)
        assert all(count == 0 for count in (await row_counts(session)).values())

        restored = await BackupService(session).restore(data)
        after = await row_counts(session)

        assert before == after
        assert restored == before

    @pytest.mark.asyncio
    async def test_restore_refuses_missing_alembic_revision(self, session: AsyncSession) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(
                "metadata.json",
                json.dumps({"version": "1", "tables": {}}),
            )
        with pytest.raises(ValidationError, match="alembic_revision"):
            await BackupService(session).restore(buf.getvalue())

    @pytest.mark.asyncio
    async def test_restore_refuses_revision_mismatch(self, session: AsyncSession) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(
                "metadata.json",
                json.dumps(
                    {
                        "version": "1",
                        "alembic_revision": "not-a-real-revision",
                        "tables": {},
                    }
                ),
            )
        with pytest.raises(ValidationError, match="does not match"):
            await BackupService(session).restore(buf.getvalue())

    @pytest.mark.asyncio
    async def test_restore_fails_on_unknown_columns(self, session: AsyncSession) -> None:
        data = await BackupService(session).export()
        with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
            rewritten = io.BytesIO()
            with zipfile.ZipFile(rewritten, "w") as out:
                for name in zf.namelist():
                    if name == "accounts.json":
                        out.writestr(
                            name,
                            json.dumps(
                                [
                                    {
                                        "id": 1,
                                        "name": "X",
                                        "type": "checking",
                                        "balance": "0.00",
                                        "currency": "PLN",
                                        "not_a_real_column": "oops",
                                    }
                                ]
                            ),
                        )
                    else:
                        out.writestr(name, zf.read(name))

        with pytest.raises(ValidationError, match="unknown columns"):
            await BackupService(session).restore(rewritten.getvalue())

    @pytest.mark.asyncio
    async def test_restore_clears_tables_absent_from_hybrid_state(
        self, session: AsyncSession
    ) -> None:
        """Restoring must DELETE every ORM table, not only those in the ZIP payload."""
        await seed_every_model(session)
        before = await row_counts(session)
        data = await BackupService(session).export()

        # Post-export orphan: a restore that only wiped tables present in the ZIP
        # with rows would leave this behind. Full-schema DELETE clears it.
        session.add(Payee(name="Orphan Payee"))
        await session.commit()
        assert await session.scalar(select(func.count()).select_from(Payee)) == (
            before["payees"] + 1
        )

        await BackupService(session).restore(data)
        after = await row_counts(session)
        assert after == before
        names = list(await session.scalars(select(Payee.name)))
        assert "Orphan Payee" not in names
