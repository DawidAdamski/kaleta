# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for IntegrityService foreign_key_check."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import ValidationError
from kaleta.services.integrity_service import IntegrityService
from tests.conftest import _USE_POSTGRES


@pytest.mark.skipif(_USE_POSTGRES, reason="SQLite-only integrity PRAGMA")
class TestIntegrityService:
    @pytest.mark.asyncio
    async def test_clean_database_returns_empty(self, session: AsyncSession) -> None:
        """Covers: KAL-INT-001"""
        violations = await IntegrityService(session).foreign_key_check()
        assert violations == []

    @pytest.mark.asyncio
    async def test_reports_planted_orphan(self, session: AsyncSession) -> None:
        """Covers: KAL-INT-002"""
        await session.execute(text("PRAGMA foreign_keys=OFF"))
        await session.execute(
            text(
                "INSERT INTO accounts (name, type, balance, currency, institution_id) "
                "VALUES ('Orphan acct', 'checking', 0, 'PLN', 99999)"
            )
        )
        await session.commit()
        await session.execute(text("PRAGMA foreign_keys=ON"))

        violations = await IntegrityService(session).foreign_key_check()
        assert len(violations) >= 1
        assert any(v.table == "accounts" and v.parent == "institutions" for v in violations)

    @pytest.mark.asyncio
    async def test_rejects_non_sqlite(
        self, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        svc = IntegrityService(session)

        async def _not_sqlite() -> bool:
            return False

        monkeypatch.setattr(svc, "is_sqlite", _not_sqlite)
        with pytest.raises(ValidationError, match="only available for SQLite"):
            await svc.foreign_key_check()
