# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration coverage for Settings → Data backup/restore.

Covers: KAL-SET-014, KAL-SET-015, KAL-SET-016
"""

from __future__ import annotations

import io
import json
import zipfile

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import ValidationError
from kaleta.services.backup_service import (
    BackupService,
    _backup_tables,
    _current_alembic_revision,
)
from tests.backup_helpers import row_counts, seed_every_model, wipe_all


@pytest.mark.asyncio
async def test_export_includes_every_table_and_alembic_revision(session: AsyncSession) -> None:
    """Covers: KAL-SET-014"""
    await seed_every_model(session)
    data = await BackupService(session).export()

    filename = BackupService.export_filename()
    assert filename.startswith("kaleta_backup_")
    assert filename.endswith(".zip")

    with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
        meta = json.loads(zf.read("metadata.json"))
        names = set(zf.namelist())

    assert meta["alembic_revision"] == _current_alembic_revision()
    for table in _backup_tables():
        assert f"{table}.json" in names
        assert table in meta["tables"]


@pytest.mark.asyncio
async def test_restore_round_trip_preserves_all_row_counts(session: AsyncSession) -> None:
    """Covers: KAL-SET-015"""
    await seed_every_model(session)
    before = await row_counts(session)
    assert all(count >= 1 for count in before.values()), before

    data = await BackupService(session).export()
    await wipe_all(session)
    restored = await BackupService(session).restore(data)
    after = await row_counts(session)

    assert before == after
    assert restored == before


@pytest.mark.asyncio
async def test_restore_refuses_schema_revision_mismatch(session: AsyncSession) -> None:
    """Covers: KAL-SET-016"""
    await seed_every_model(session)
    before = await row_counts(session)

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

    assert await row_counts(session) == before


@pytest.mark.asyncio
async def test_restore_preserves_an_encrypted_secret(session: AsyncSession) -> None:
    """Covers: KAL-SET-015

    An encrypted column is a BLOB, which JSON cannot hold, and the value the
    export carries is ciphertext. Getting either half wrong leaves a restored
    row that reads back as noise — and a two-factor secret that reads back as
    noise locks the owner out of their own ledger after a restore.
    """
    from sqlalchemy import select

    from kaleta.models import UserMfa

    await seed_every_model(session)
    before = (await session.execute(select(UserMfa.totp_secret))).scalar_one()
    assert before == "JBSWY3DPEHPK3PXP"

    data = await BackupService(session).export()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        exported = json.loads(zf.read("user_mfa.json"))
    assert before not in json.dumps(exported), "the backup must carry ciphertext, not the secret"

    await wipe_all(session)
    await BackupService(session).restore(data)
    session.expire_all()
    after = (await session.execute(select(UserMfa.totp_secret))).scalar_one()
    assert after == before
