# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration coverage for interactive CLI password reset.

Covers: KAL-AUTH-007, KAL-AUTH-018
"""

from __future__ import annotations

import asyncio
import io
from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import kaleta.models  # noqa: F401 — register ORM tables on Base.metadata
from kaleta.cli.reset_password import ResetPasswordCli
from kaleta.db import configure_database
from kaleta.db import types as types_mod
from kaleta.db.base import Base
from kaleta.exceptions import ValidationError
from kaleta.services.auth_service import AuthService
from tests.conftest import _POSTGRES_URL, _USE_POSTGRES


@pytest.fixture
def global_db_restored() -> Generator[None]:
    """Put the shared session factory back after the CLI has repointed it.

    ``ResetPasswordCli`` calls ``configure_database`` on the URL it was given,
    which is a one-shot process in production and a landmine in a test run:
    every later test reaching for ``with_session`` would get this test's
    throwaway SQLite file. The two older tests here dodge it by skipping the
    whole case under postgres; restoring the URL is what that skip was
    standing in for, and it keeps these cases running on both backends.

    Under postgres only, because that is where a shared URL exists to put
    back. On the default SQLite run the factory is left pointing at this
    test's ``tmp_path`` file — the same leak the two older tests already
    have, and harmless there because every test that matters builds its own
    engine. Worth closing if a SQLite test ever starts depending on the
    global factory.
    """
    yield
    if _USE_POSTGRES:
        configure_database(_POSTGRES_URL, debug=True)


async def _prepare_db(db_url: str, *, username: str | None, password: str | None) -> None:
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    if username is not None and password is not None:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            await AuthService(session).create_user(username, password)
    await engine.dispose()


async def _enrol_mfa(db_url: str, username: str) -> None:
    import time

    import pyotp

    from kaleta.services.mfa_service import TOTP_INTERVAL, MfaService

    engine = create_async_engine(db_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            user = await AuthService(session).get_user_by_username(username)
            assert user is not None
            mfa = MfaService(session)
            enrolment = await mfa.begin_enrolment(user.id)
            code = pyotp.TOTP(enrolment.secret, interval=TOTP_INTERVAL).at(int(time.time()))
            await mfa.confirm_enrolment(user.id, str(code))
    finally:
        await engine.dispose()


async def _mfa_enabled(db_url: str, username: str) -> bool:
    from kaleta.services.mfa_service import MfaService

    engine = create_async_engine(db_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            user = await AuthService(session).get_user_by_username(username)
            assert user is not None
            return await MfaService(session).is_enabled(user.id)
    finally:
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


def test_reset_password_cli_can_drop_the_second_factor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, global_db_restored: None
) -> None:
    """Covers: KAL-AUTH-018

    A self-hoster whose phone is gone still has the shell. Without this the
    only way back into their own ledger would be editing the database by hand.
    """
    db_path = tmp_path / "kaleta.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    asyncio.run(_prepare_db(db_url, username="alice", password="old-password-1"))
    asyncio.run(_enrol_mfa(db_url, "alice"))
    assert asyncio.run(_mfa_enabled(db_url, "alice")) is True

    monkeypatch.setattr("kaleta.cli.reset_password.get_db_url", lambda: db_url)
    prompts = iter(["new-password-9", "new-password-9"])
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = ResetPasswordCli(
        get_password=lambda _prompt: next(prompts),
        stdout=stdout,
        stderr=stderr,
        disable_mfa=True,
    ).run()

    assert code == 0
    assert stderr.getvalue() == ""
    assert "Two-factor enrolments removed: 1" in stdout.getvalue()
    assert asyncio.run(_mfa_enabled(db_url, "alice")) is False
    assert asyncio.run(_authenticate(db_url, "alice", "new-password-9")) is True


def test_reset_password_cli_leaves_the_second_factor_alone_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, global_db_restored: None
) -> None:
    """Covers: KAL-AUTH-018 — a password reset is not a way around the second factor."""
    db_path = tmp_path / "kaleta.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    asyncio.run(_prepare_db(db_url, username="alice", password="old-password-1"))
    asyncio.run(_enrol_mfa(db_url, "alice"))

    monkeypatch.setattr("kaleta.cli.reset_password.get_db_url", lambda: db_url)
    prompts = iter(["new-password-9", "new-password-9"])
    stdout = io.StringIO()
    code = ResetPasswordCli(
        get_password=lambda _prompt: next(prompts),
        stdout=stdout,
    ).run()

    assert code == 0
    assert "Two-factor" not in stdout.getvalue()
    assert asyncio.run(_mfa_enabled(db_url, "alice")) is True


def test_reset_password_cli_works_after_a_key_rotation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, global_db_restored: None
) -> None:
    """Covers: KAL-AUTH-018

    Rotating KALETA_SECRET_KEY makes every stored secret unreadable, and this
    command is the documented way back. Anything on its path that decrypted a
    secret to do its job would shut the one door that is left.
    """
    db_path = tmp_path / "kaleta.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    asyncio.run(_prepare_db(db_url, username="alice", password="old-password-1"))
    asyncio.run(_enrol_mfa(db_url, "alice"))

    monkeypatch.setattr(types_mod, "_key_source", lambda: b"rotated-key-" + b"z" * 20)
    monkeypatch.setattr("kaleta.cli.reset_password.get_db_url", lambda: db_url)
    prompts = iter(["new-password-9", "new-password-9"])
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = ResetPasswordCli(
        get_password=lambda _prompt: next(prompts),
        stdout=stdout,
        stderr=stderr,
        disable_mfa=True,
    ).run()

    assert code == 0, stderr.getvalue()
    assert "Two-factor enrolments removed: 1" in stdout.getvalue()
    assert asyncio.run(_mfa_enabled(db_url, "alice")) is False
    assert asyncio.run(_authenticate(db_url, "alice", "new-password-9")) is True


def test_reset_password_cli_only_claims_a_removal_that_happened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, global_db_restored: None
) -> None:
    """Covers: KAL-AUTH-018

    The audience for this message is a locked-out self-hoster following
    SECURITY.md — the one person who cannot check whether their factor is
    still on. It must not guess in either direction.
    """
    db_path = tmp_path / "kaleta.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    asyncio.run(_prepare_db(db_url, username="alice", password="old-password-1"))
    asyncio.run(_enrol_mfa(db_url, "alice"))

    monkeypatch.setattr("kaleta.cli.reset_password.get_db_url", lambda: db_url)

    def boom(_self: object, _password: str) -> None:
        raise ValidationError("Password too short")

    monkeypatch.setattr("kaleta.services.auth_service.AuthService.reset_password", boom)
    prompts = iter(["new-password-9", "new-password-9"])
    stderr = io.StringIO()
    code = ResetPasswordCli(
        get_password=lambda _prompt: next(prompts),
        stderr=stderr,
        disable_mfa=True,
    ).run()

    assert code == 1
    assert "Two-factor enrolments were already removed: 1" in stderr.getvalue()
    # And it is true: the removal committed before the password step ran.
    assert asyncio.run(_mfa_enabled(db_url, "alice")) is False
    assert asyncio.run(_authenticate(db_url, "alice", "old-password-1")) is True


def test_reset_password_cli_says_nothing_about_a_removal_that_did_not_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, global_db_restored: None
) -> None:
    """Covers: KAL-AUTH-018 — the other direction: never claim a removal that
    never happened."""
    db_path = tmp_path / "kaleta.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    asyncio.run(_prepare_db(db_url, username="alice", password="old-password-1"))
    asyncio.run(_enrol_mfa(db_url, "alice"))

    monkeypatch.setattr("kaleta.cli.reset_password.get_db_url", lambda: db_url)

    async def boom(_self: object) -> int:
        raise ValidationError("Could not read the enrolments")

    monkeypatch.setattr("kaleta.services.mfa_service.MfaService.disable_all", boom)
    prompts = iter(["new-password-9", "new-password-9"])
    stderr = io.StringIO()
    code = ResetPasswordCli(
        get_password=lambda _prompt: next(prompts),
        stderr=stderr,
        disable_mfa=True,
    ).run()

    assert code == 1
    assert "already removed" not in stderr.getvalue()
    assert asyncio.run(_mfa_enabled(db_url, "alice")) is True
