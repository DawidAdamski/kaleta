# SPDX-License-Identifier: AGPL-3.0-or-later
"""``scripts/encrypt_database.py`` switches an existing database's encryption on and off.

Covers: KAL-ENC-009
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import kaleta.models  # noqa: F401 — register every table
from kaleta.config import settings
from kaleta.db.base import Base
from kaleta.db.types import TEXT_FORMAT_AES_GCM, TEXT_FORMAT_PLAIN, exact_index, use_data_key
from kaleta.models.local_key_material import LocalKeyMaterial
from kaleta.models.payee import Payee
from kaleta.services import AuthService
from kaleta.services.key_service import open_local_data_key

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "scripts" / "encrypt_database.py"
PASSPHRASE = "the household passphrase"


async def _plaintext_database(db_url: str) -> None:
    engine = create_async_engine(db_url)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            await AuthService(session).create_user("ania", "login-password-1")
            session.add(Payee(name="Biedronka"))
            await session.commit()
    finally:
        await engine.dispose()


async def _raw_payee_name(db_url: str) -> bytes:
    engine = create_async_engine(db_url)
    try:
        async with engine.connect() as conn:
            return bytes((await conn.execute(text("SELECT name FROM payees"))).scalar_one())
    finally:
        await engine.dispose()


def _run(db_url: str, home: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=PROJECT_ROOT,
        env={
            **os.environ,
            "HOME": str(home),
            "KALETA_DB_URL": db_url,
            "KALETA_ENCRYPTION": "passphrase",
            "KALETA_DATA_PASSPHRASE": PASSPHRASE,
            "KALETA_BACKUP_DIR": str(home / "backups"),
        },
        check=False,
        capture_output=True,
        text=True,
    )


def test_encrypt_then_decrypt_an_existing_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Covers: KAL-ENC-009"""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'ledger.db'}"
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(settings, "encryption", "off")
    asyncio.run(_plaintext_database(db_url))
    assert asyncio.run(_raw_payee_name(db_url))[0] == TEXT_FORMAT_PLAIN

    encrypted = _run(db_url, home)

    assert encrypted.returncode == 0, encrypted.stderr or encrypted.stdout
    assert "recovery code" in encrypted.stdout.lower()
    assert list((home / "backups").glob("kaleta-pre-encryption-*.zip"))
    stored = asyncio.run(_raw_payee_name(db_url))
    assert stored[0] == TEXT_FORMAT_AES_GCM
    assert b"Biedronka" not in stored

    monkeypatch.setattr(settings, "encryption", "passphrase")

    async def _read_back() -> str:
        engine = create_async_engine(db_url)
        try:
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory() as session:
                data_key = await open_local_data_key(session, PASSPHRASE)
                with use_data_key(data_key):
                    found = await session.execute(
                        select(Payee).where(Payee.name_bidx == exact_index("Biedronka"))
                    )
                    return found.scalar_one().name
        finally:
            await engine.dispose()

    assert asyncio.run(_read_back()) == "Biedronka"

    decrypted = _run(db_url, home, "--decrypt")

    assert decrypted.returncode == 0, decrypted.stderr or decrypted.stdout
    assert asyncio.run(_raw_payee_name(db_url)) == bytes([TEXT_FORMAT_PLAIN]) + b"Biedronka"

    async def _holders() -> int:
        engine = create_async_engine(db_url)
        try:
            async with engine.connect() as conn:
                count = await conn.execute(select(func.count()).select_from(LocalKeyMaterial))
                return int(count.scalar_one())
        finally:
            await engine.dispose()

    assert asyncio.run(_holders()) == 0


def test_encrypting_needs_the_setting(tmp_path: Path) -> None:
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'ledger.db'}"
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=PROJECT_ROOT,
        env={
            **os.environ,
            "HOME": str(tmp_path),
            "KALETA_DB_URL": db_url,
            "KALETA_ENCRYPTION": "off",
        },
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "KALETA_ENCRYPTION=passphrase" in result.stderr
