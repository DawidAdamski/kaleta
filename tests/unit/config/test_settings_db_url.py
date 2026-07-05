# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for KALETA_DB_URL async driver normalization."""

from __future__ import annotations

import logging

import pytest

from kaleta.config.settings import Settings, normalize_db_url


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("sqlite:///kaleta.db", "sqlite+aiosqlite:///kaleta.db"),
        ("sqlite:////absolute/path.db", "sqlite+aiosqlite:////absolute/path.db"),
        ("sqlite+aiosqlite:///kaleta.db", "sqlite+aiosqlite:///kaleta.db"),
        (
            "postgresql://user:pass@localhost:5432/kaleta",
            "postgresql+asyncpg://user:pass@localhost:5432/kaleta",
        ),
        (
            "postgres://user:pass@localhost:5432/kaleta",
            "postgresql+asyncpg://user:pass@localhost:5432/kaleta",
        ),
        (
            "postgresql+asyncpg://user:pass@localhost:5432/kaleta",
            "postgresql+asyncpg://user:pass@localhost:5432/kaleta",
        ),
        ("mysql://localhost/kaleta", "mysql://localhost/kaleta"),
    ],
)
def test_normalize_db_url(raw: str, expected: str) -> None:
    assert normalize_db_url(raw) == expected


def test_settings_applies_db_url_normalization() -> None:
    settings = Settings.model_validate(
        {"debug": True, "db_url": "sqlite:///tmp.db"},
    )
    assert settings.db_url == "sqlite+aiosqlite:///tmp.db"


def test_settings_logs_db_url_rewrite(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="kaleta.config.settings"):
        Settings.model_validate({"debug": True, "db_url": "sqlite:///tmp.db"})
    assert any("KALETA_DB_URL rewritten" in record.message for record in caplog.records)
