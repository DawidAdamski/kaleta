# SPDX-License-Identifier: AGPL-3.0-or-later
"""Interactive ``kaleta --reset-password`` command.

``--disable-mfa`` drops every second-factor enrolment at the same time. It is
the local equivalent of a recovery code: a self-hoster who still has shell
access to the machine already has the database file, so requiring a code from
a lost phone would only lock them out of their own ledger.
"""

from __future__ import annotations

import asyncio
import getpass
import logging
import sys
from collections.abc import Callable
from typing import TextIO

from kaleta.config import settings
from kaleta.config.setup_config import get_db_url
from kaleta.db import AsyncSessionFactory, configure_database
from kaleta.exceptions import KaletaError
from kaleta.services.auth_service import AuthService
from kaleta.services.mfa_service import MfaService

log = logging.getLogger(__name__)

GetPass = Callable[[str], str]
PrintFn = Callable[..., None]


class ResetPasswordCli:
    """Prompt for a new password and update the sole user on the configured DB."""

    def __init__(
        self,
        *,
        get_password: GetPass | None = None,
        stdout: TextIO | None = None,
        stderr: TextIO | None = None,
        disable_mfa: bool = False,
    ) -> None:
        self._get_password = get_password or getpass.getpass
        self._stdout = stdout or sys.stdout
        self._stderr = stderr or sys.stderr
        self._disable_mfa = disable_mfa

    def run(self) -> int:
        db_url = get_db_url()
        if not db_url:
            self._stderr.write(
                "No database configured in ~/.kaleta/config.json.\n"
                "Run `uv run kaleta` once to complete setup, then retry.\n"
            )
            return 1

        try:
            new_password = self._get_password("New password: ")
            confirm = self._get_password("Confirm password: ")
        except (EOFError, KeyboardInterrupt):
            self._stderr.write("\nPassword reset cancelled.\n")
            return 1

        if new_password != confirm:
            self._stderr.write("Passwords do not match.\n")
            return 1

        try:
            username, disabled = asyncio.run(self._reset(db_url, new_password))
        except KaletaError as exc:
            self._stderr.write(f"{exc.message}\n")
            return 1
        except Exception:
            log.exception("Password reset failed")
            self._stderr.write("Password reset failed. See logs for details.\n")
            return 1

        self._stdout.write(
            f"Password updated for user {username!r}.\n"
            "Existing browser sessions may still work until you sign out or clear "
            "site data; API bearer tokens are unchanged.\n"
        )
        if self._disable_mfa:
            self._stdout.write(
                f"Two-factor enrolments removed: {disabled}. "
                "Set it up again in Settings \u2192 Security.\n"
            )
        return 0

    async def _reset(self, db_url: str, new_password: str) -> tuple[str, int]:
        configure_database(db_url, debug=settings.debug)
        try:
            async with AsyncSessionFactory() as session:
                # Order matters: the enrolments go first. If that fails the
                # password is untouched and the owner can try again, rather
                # than being left with a new password and the second factor
                # they asked to be rid of still in the way.
                disabled = await MfaService(session).disable_all() if self._disable_mfa else 0
                user = await AuthService(session).reset_password(new_password)
                return user.username, disabled
        finally:
            await AsyncSessionFactory.dispose()
