# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration coverage for scripts/reset_demo.py.

Covers: KAL-PLT-002
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import kaleta.models  # noqa: F401 — register ORM tables on Base.metadata
from kaleta.db.base import Base
from kaleta.services.auth_service import AuthService

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESET_SCRIPT = PROJECT_ROOT / "scripts" / "reset_demo.py"


async def _prepare_db(db_url: str) -> None:
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="subprocess env demo reset test uses POSIX sqlite paths",
)
def test_reset_demo_script_seeds_demo_user(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Covers: KAL-PLT-002"""
    db_path = tmp_path / "demo.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    asyncio.run(_prepare_db(db_url))

    env = {
        **os.environ,
        "HOME": str(home),
        "KALETA_DEBUG": "true",
        "KALETA_DEMO": "true",
        "KALETA_DB_URL": db_url,
    }
    proc = subprocess.run(
        [sys.executable, str(RESET_SCRIPT)],
        cwd=PROJECT_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout

    async def _verify() -> None:
        engine = create_async_engine(db_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                auth = AuthService(session)
                user = await auth.authenticate("demo", "demo-kaleta")
                assert user is not None
                assert user.username == "demo"
        finally:
            await engine.dispose()

    asyncio.run(_verify())

    config = home / ".kaleta" / "config.json"
    assert config.is_file()
    assert "demo" in config.read_text(encoding="utf-8")


def test_reset_demo_refuses_without_demo_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "demo.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    env = {
        **os.environ,
        "HOME": str(home),
        "KALETA_DEBUG": "true",
        "KALETA_DB_URL": db_url,
    }
    proc = subprocess.run(
        [sys.executable, str(RESET_SCRIPT)],
        cwd=PROJECT_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "KALETA_DEMO" in (proc.stderr or proc.stdout)
