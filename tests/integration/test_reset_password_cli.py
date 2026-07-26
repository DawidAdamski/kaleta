# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration coverage for interactive CLI password reset.

Covers: KAL-AUTH-007
"""

from __future__ import annotations

import asyncio
import io
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import kaleta.models  # noqa: F401 — register ORM tables on Base.metadata
from kaleta.cli.reset_password import ResetPasswordCli
from kaleta.db.base import Base
from kaleta.services.auth_service import AuthService
from tests.conftest import _USE_POSTGRES


async def _prepare_db(db_url: str, *, username: str | None, password: str | None) -> None:
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    if username is not None and password is not None:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            await AuthService(session).create_user(username, password)
    await engine.dispose()


async def _authenticate(db_url: str, username: str, password: str) -> bool:
    engine = create_async_engine(db_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            user = await AuthService(session).authenticate(username, password)
            return user is not None
    finally:
        await engine.dispose()


@pytest.mark.skipif(_USE_POSTGRES, reason="CLI reset integration uses on-disk SQLite")
def test_reset_password_cli_updates_configured_user(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Covers: KAL-AUTH-007"""
    db_path = tmp_path / "kaleta.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    asyncio.run(_prepare_db(db_url, username="alice", password="old-password-1"))

    monkeypatch.setattr("kaleta.cli.reset_password.get_db_url", lambda: db_url)
    prompts = iter(["new-password-9", "new-password-9"])
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = ResetPasswordCli(
        get_password=lambda _prompt: next(prompts),
        stdout=stdout,
        stderr=stderr,
    ).run()

    assert code == 0
    assert "alice" in stdout.getvalue()
    assert stderr.getvalue() == ""
    assert asyncio.run(_authenticate(db_url, "alice", "new-password-9")) is True
    assert asyncio.run(_authenticate(db_url, "alice", "old-password-1")) is False


@pytest.mark.skipif(_USE_POSTGRES, reason="CLI reset integration uses on-disk SQLite")
def test_reset_password_cli_no_user_points_to_bootstrap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Covers: KAL-AUTH-007"""
    db_path = tmp_path / "empty.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    asyncio.run(_prepare_db(db_url, username=None, password=None))

    monkeypatch.setattr("kaleta.cli.reset_password.get_db_url", lambda: db_url)
    prompts = iter(["new-password-9", "new-password-9"])
    stderr = io.StringIO()
    code = ResetPasswordCli(
        get_password=lambda _prompt: next(prompts),
        stderr=stderr,
    ).run()

    assert code == 1
    assert "first-run bootstrap" in stderr.getvalue()
