"""Playwright e2e test configuration.

Prerequisites:
  1. Install browsers once:  uv run playwright install chromium
  2. Start the app:          uv run kaleta
  3. Run tests:              uv run pytest tests/e2e/ -v

The conftest configures kaleta's AsyncSessionFactory to connect to the same
database the running app is using, so seed helpers in test modules write to
the correct DB.
"""

from __future__ import annotations

import pytest

BASE_URL = "http://localhost:8080"
API_BASE = f"{BASE_URL}/api/v1"


def _configure_db_for_tests() -> None:
    """Point kaleta's AsyncSessionFactory at the DB the running app uses."""
    from kaleta.config.setup_config import get_db_url
    from kaleta.db import configure_database

    db_url = get_db_url()
    if db_url:
        configure_database(db_url)


# Configure the DB once when this module is imported (before any test is collected)
_configure_db_for_tests()


@pytest.fixture(scope="session")
def base_url() -> str:
    return BASE_URL
