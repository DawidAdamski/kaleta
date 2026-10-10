# SPDX-License-Identifier: AGPL-3.0-or-later
"""KALETA_DB_URL: PostgreSQL only, rewritten to the async driver.

Covers: KAL-SET-030
"""

from __future__ import annotations

import logging

import pytest
from pydantic import ValidationError

from kaleta.config.settings import Settings, normalize_db_url


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
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
    """Covers: KAL-SET-030"""
    settings = Settings.model_validate(
        {"debug": True, "db_url": "postgresql://kaleta@localhost:5432/kaleta"},
    )
    assert settings.db_url == "postgresql+asyncpg://kaleta@localhost:5432/kaleta"


def test_settings_logs_db_url_rewrite(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="kaleta.config.settings"):
        Settings.model_validate({"debug": True, "db_url": "postgres://kaleta@db/kaleta"})
    assert any("KALETA_DB_URL rewritten" in record.message for record in caplog.records)


@pytest.mark.parametrize(
    "url",
    [
        "sqlite:///kaleta.db",
        "sqlite+aiosqlite:////home/u/.kaleta/kaleta.db",
        "mysql://db/k",
        "postgresql+psycopg2://kaleta@db/kaleta",
    ],
)
def test_a_url_that_is_not_postgresql_is_refused(url: str) -> None:
    """Covers: KAL-SET-030"""
    with pytest.raises(ValidationError) as excinfo:
        Settings.model_validate({"debug": True, "db_url": url})
    message = str(excinfo.value)
    assert "PostgreSQL 16+" in message
    assert "ADR-38" in message


def test_a_refused_url_is_not_echoed_with_its_password() -> None:
    with pytest.raises(ValidationError) as excinfo:
        Settings.model_validate({"debug": True, "db_url": "mysql://u:s3cret@db/k"})
    assert "s3cret" not in str(excinfo.value)
