# SPDX-License-Identifier: AGPL-3.0-or-later
"""KALETA_AUTH_BACKEND / KALETA_ENCRYPTION — one layout, and what may run on it (ADR-38).

Every instance is a registry and a schema per family. Logins are ``local``
(kept in the registry) or ``supabase``, or ``fake`` on a developer's laptop
(``KALETA_DEBUG=true`` only). Encryption is on; ``off`` is a laptop setting too.
The single-family switches are gone and say where they went.

Covers: KAL-TEN-011, KAL-TEN-023
"""

from __future__ import annotations

import io
import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from kaleta import main as main_mod
from kaleta.config.settings import Settings

_SUPABASE = {
    "supabase_url": "https://project.supabase.co",
    "supabase_anon_key": "anon-key",
}
_PRODUCTION = {"debug": False, "secret_key": "a-real-secret-for-this-test"}


def test_defaults_are_local_logins_with_encryption_on() -> None:
    """Covers: KAL-TEN-023"""
    settings = Settings.model_validate({"debug": True})
    assert (settings.auth_backend, settings.encryption_enabled) == ("local", True)


def test_supabase_is_accepted() -> None:
    settings = Settings.model_validate({"debug": True, "auth_backend": "supabase", **_SUPABASE})
    assert settings.auth_backend == "supabase"


def test_supabase_without_its_url_and_key_is_refused() -> None:
    with pytest.raises(ValidationError, match="KALETA_SUPABASE_URL and KALETA_SUPABASE_ANON_KEY"):
        Settings.model_validate({"debug": True, "auth_backend": "supabase"})


def test_the_fake_backend_is_accepted_with_debug() -> None:
    """Covers: KAL-TEN-011"""
    settings = Settings.model_validate({"debug": True, "auth_backend": "fake"})
    assert settings.auth_backend == "fake"


def test_the_fake_backend_is_refused_without_debug() -> None:
    """Covers: KAL-TEN-011"""
    with pytest.raises(ValidationError, match="KALETA_AUTH_BACKEND=fake is accepted only with"):
        Settings.model_validate({**_PRODUCTION, "auth_backend": "fake"})


def test_encryption_off_is_refused_without_debug() -> None:
    """Covers: KAL-TEN-023"""
    with pytest.raises(ValidationError, match="KALETA_ENCRYPTION=off is accepted only with"):
        Settings.model_validate({**_PRODUCTION, "encryption": "off"})


def test_encryption_off_is_accepted_with_debug() -> None:
    settings = Settings.model_validate({"debug": True, "encryption": "off"})
    assert not settings.encryption_enabled


def test_mode_names_are_case_insensitive() -> None:
    settings = Settings.model_validate(
        {"debug": True, "auth_backend": "Supabase", "encryption": " PASSPHRASE ", **_SUPABASE}
    )
    assert (settings.auth_backend, settings.encryption) == ("supabase", "passphrase")


def test_a_leftover_kaleta_tenancy_is_named_and_ignored(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Covers: KAL-TEN-023"""
    monkeypatch.setenv("KALETA_TENANCY", "single")
    with caplog.at_level(logging.WARNING, logger="kaleta.config.settings"):
        Settings.model_validate({"debug": True})
    assert "KALETA_TENANCY is no longer read" in caplog.text


def test_importing_the_config_with_local_logins_starts(tmp_path: Path) -> None:
    """ADR-38: the layout a homelab runs imports cleanly, as a process."""
    env = {**os.environ, "HOME": str(tmp_path), "KALETA_DEBUG": "true"}
    env.pop("KALETA_TENANCY", None)
    env["KALETA_AUTH_BACKEND"] = "local"
    result = subprocess.run(
        [sys.executable, "-c", "import kaleta.config"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("flags", [["--reset-password"], ["--disable-mfa"]])
def test_the_old_reset_flags_name_kaleta_admin(
    flags: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Covers: KAL-TEN-023

    Whoever types this has lost a password or a phone and is following an old
    SECURITY.md. Booting the app and saying nothing is the worst answer there is.
    """
    stderr = io.StringIO()
    monkeypatch.setattr(main_mod.sys, "argv", ["kaleta", *flags])
    monkeypatch.setattr(main_mod.sys, "stderr", stderr)
    monkeypatch.setattr(main_mod, "run_web", lambda: pytest.fail("the app must not start"))

    with pytest.raises(SystemExit) as exit_info:
        main_mod.main()

    assert exit_info.value.code == 2
    assert "kaleta-admin reset-password <e-mail> [--disable-mfa]" in stderr.getvalue()
