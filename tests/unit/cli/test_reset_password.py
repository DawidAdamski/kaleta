# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for the interactive reset-password CLI."""

from __future__ import annotations

import io

import pytest

from kaleta.cli.reset_password import ResetPasswordCli
from kaleta.exceptions import NotFoundError


class TestResetPasswordCli:
    def test_refuses_when_no_database_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "kaleta.cli.reset_password.get_db_url",
            lambda: None,
        )
        stderr = io.StringIO()
        code = ResetPasswordCli(stderr=stderr).run()
        assert code == 1
        assert "~/.kaleta/config.json" in stderr.getvalue()
        assert "uv run kaleta" in stderr.getvalue()

    def test_refuses_password_mismatch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "kaleta.cli.reset_password.get_db_url",
            lambda: "sqlite+aiosqlite:///:memory:",
        )
        prompts = iter(["new-password-9", "different-password"])
        stderr = io.StringIO()
        code = ResetPasswordCli(
            get_password=lambda _prompt: next(prompts),
            stderr=stderr,
        ).run()
        assert code == 1
        assert "Passwords do not match." in stderr.getvalue()

    def test_surfaces_domain_errors(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "kaleta.cli.reset_password.get_db_url",
            lambda: "sqlite+aiosqlite:///:memory:",
        )

        async def _fail(
            _self: ResetPasswordCli,
            _db_url: str,
            _password: str,
            _note_removed: object,
        ) -> str:
            raise NotFoundError(
                "No user found. Create an account via the first-run bootstrap "
                "(open the app and use Create account)."
            )

        monkeypatch.setattr(ResetPasswordCli, "_reset", _fail)
        prompts = iter(["new-password-9", "new-password-9"])
        stderr = io.StringIO()
        code = ResetPasswordCli(
            get_password=lambda _prompt: next(prompts),
            stderr=stderr,
        ).run()
        assert code == 1
        assert "first-run bootstrap" in stderr.getvalue()

    def test_success_says_every_browser_was_signed_out(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Covers: KAL-AUTH-028"""
        monkeypatch.setattr(
            "kaleta.cli.reset_password.get_db_url",
            lambda: "sqlite+aiosqlite:///:memory:",
        )

        async def _ok(
            _self: ResetPasswordCli,
            _db_url: str,
            _password: str,
            _note_removed: object,
        ) -> tuple[str, int]:
            return "owner", 0

        monkeypatch.setattr(ResetPasswordCli, "_reset", _ok)
        prompts = iter(["new-password-9", "new-password-9"])
        stdout = io.StringIO()
        code = ResetPasswordCli(
            get_password=lambda _prompt: next(prompts),
            stdout=stdout,
        ).run()
        assert code == 0
        assert (
            "All browser sessions have been signed out; API bearer tokens are unchanged."
            in stdout.getvalue()
        )
        assert "may still work" not in stdout.getvalue()
