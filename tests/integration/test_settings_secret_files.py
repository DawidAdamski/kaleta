# SPDX-License-Identifier: AGPL-3.0-or-later
"""Settings from secret files: how ``docker-compose.yml`` hands Kaleta its secrets.

Covers: KAL-SET-031
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kaleta.config.settings import _SECRETS_DIR, Settings


def _write_secrets(directory: Path) -> None:
    (directory / "kaleta_db_url").write_text("postgresql://kaleta:pw@db:5432/kaleta\n")
    (directory / "kaleta_secret_key").write_text("a-key-from-a-file\n")


def test_the_secret_files_live_where_docker_and_podman_put_them() -> None:
    """Covers: KAL-SET-031"""
    assert Path("/run/secrets") == _SECRETS_DIR


def test_settings_are_read_from_secret_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Covers: KAL-SET-031"""
    monkeypatch.delenv("KALETA_DB_URL", raising=False)
    monkeypatch.delenv("KALETA_SECRET_KEY", raising=False)
    _write_secrets(tmp_path)

    settings = Settings(_env_file=None, _secrets_dir=tmp_path)

    assert settings.db_url == "postgresql+asyncpg://kaleta:pw@db:5432/kaleta"
    assert settings.secret_key == "a-key-from-a-file"


def test_an_environment_variable_wins_over_its_secret_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Covers: KAL-SET-031"""
    monkeypatch.setenv("KALETA_SECRET_KEY", "a-key-from-the-environment")
    _write_secrets(tmp_path)

    settings = Settings(_env_file=None, _secrets_dir=tmp_path)

    assert settings.secret_key == "a-key-from-the-environment"
