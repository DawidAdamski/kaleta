"""Playwright e2e test configuration.

Prerequisites:
  1. Install browsers once:  uv run playwright install chromium
  2. Start the app:          KALETA_DB_URL=sqlite+aiosqlite:///test_e2e.db uv run kaleta
  3. Run tests:              uv run pytest tests/e2e/ -v
"""
from __future__ import annotations

import pytest

BASE_URL = "http://localhost:8080"


@pytest.fixture(scope="session")
def base_url() -> str:
    return BASE_URL
