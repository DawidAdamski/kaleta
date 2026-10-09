# SPDX-License-Identifier: AGPL-3.0-or-later
"""KALETA_TENANCY / KALETA_AUTH_BACKEND — only the two real layouts start.

Self-hosted is ``single`` + ``local``; hosted is ``multi`` + ``supabase``, or
``multi`` + ``fake`` on a developer's laptop (``KALETA_DEBUG=true`` only).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from kaleta.config.settings import Settings

_SUPABASE = {
    "supabase_url": "https://project.supabase.co",
    "supabase_anon_key": "anon-key",
}


def test_defaults_are_the_self_hosted_layout() -> None:
    settings = Settings.model_validate({"debug": True})
    assert (settings.tenancy, settings.auth_backend) == ("single", "local")


def test_multi_tenancy_with_supabase_is_accepted() -> None:
    settings = Settings.model_validate(
        {"debug": True, "tenancy": "multi", "auth_backend": "supabase", **_SUPABASE}
    )
    assert (settings.tenancy, settings.auth_backend) == ("multi", "supabase")


def test_multi_tenancy_with_the_local_backend_is_refused() -> None:
    """Refused by the settings validator, before anything else can start."""
    with pytest.raises(ValidationError, match="KALETA_TENANCY=multi requires"):
        Settings.model_validate({"debug": True, "tenancy": "multi", "auth_backend": "local"})


def test_supabase_on_a_single_tenant_database_is_refused() -> None:
    """Refused by the settings validator, before anything else can start."""
    with pytest.raises(ValidationError, match="requires KALETA_TENANCY=multi"):
        Settings.model_validate(
            {"debug": True, "tenancy": "single", "auth_backend": "supabase", **_SUPABASE}
        )


def test_supabase_without_its_url_and_key_is_refused() -> None:
    with pytest.raises(ValidationError, match="KALETA_SUPABASE_URL and KALETA_SUPABASE_ANON_KEY"):
        Settings.model_validate({"debug": True, "tenancy": "multi", "auth_backend": "supabase"})


def test_the_fake_backend_is_accepted_with_debug_on_a_multi_tenant_database() -> None:
    """Covers: KAL-TEN-011"""
    settings = Settings.model_validate({"debug": True, "tenancy": "multi", "auth_backend": "fake"})
    assert (settings.tenancy, settings.auth_backend) == ("multi", "fake")


def test_the_fake_backend_is_refused_without_debug() -> None:
    """Covers: KAL-TEN-011"""
    with pytest.raises(ValidationError, match="KALETA_AUTH_BACKEND=fake is accepted only with"):
        Settings.model_validate(
            {
                "debug": False,
                "secret_key": "a-real-secret-for-this-test",
                "tenancy": "multi",
                "auth_backend": "fake",
            }
        )


def test_the_fake_backend_is_refused_on_a_single_tenant_database() -> None:
    with pytest.raises(ValidationError, match="KALETA_AUTH_BACKEND=fake requires"):
        Settings.model_validate({"debug": True, "tenancy": "single", "auth_backend": "fake"})


def test_mode_names_are_case_insensitive() -> None:
    settings = Settings.model_validate(
        {"debug": True, "tenancy": " MULTI ", "auth_backend": "Supabase", **_SUPABASE}
    )
    assert (settings.tenancy, settings.auth_backend) == ("multi", "supabase")


def test_importing_the_config_with_multi_and_local_exits_non_zero(tmp_path: Path) -> None:
    """The acceptance criterion's own command, as a process."""
    env = {
        **os.environ,
        "HOME": str(tmp_path),
        "KALETA_DEBUG": "true",
        "KALETA_TENANCY": "multi",
        "KALETA_AUTH_BACKEND": "local",
    }
    result = subprocess.run(
        [sys.executable, "-c", "import kaleta.config"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
    )
    assert result.returncode != 0
    assert "KALETA_TENANCY=multi requires KALETA_AUTH_BACKEND=supabase" in result.stderr
