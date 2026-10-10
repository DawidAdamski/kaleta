# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration coverage for scripts/reset_demo.py on a self-hosted instance.

Covers: KAL-PLT-002
"""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from kaleta.services.local_identity_service import LocalIdentityService
from kaleta.services.setup_service import upgrade_public_to_head
from tests.suite_database import fresh_database_url

# Slow tier (test-suite-speed): reset_demo.py in a subprocess.
pytestmark = pytest.mark.slow

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESET_SCRIPT = PROJECT_ROOT / "scripts" / "reset_demo.py"


def _reset_demo(db_url: str, home: Path, **extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RESET_SCRIPT)],
        cwd=PROJECT_ROOT,
        env={
            **os.environ,
            "HOME": str(home),
            "KALETA_DEBUG": "true",
            "KALETA_AUTH_BACKEND": "local",
            "KALETA_DB_URL": db_url,
            **extra,
        },
        check=False,
        capture_output=True,
        text=True,
    )


def test_reset_demo_script_seeds_demo_user(tmp_path: Path) -> None:
    """Covers: KAL-PLT-002"""
    db_url = fresh_database_url("reset_demo")
    upgrade_public_to_head(db_url)

    proc = _reset_demo(db_url, tmp_path, KALETA_DEMO="true")
    assert proc.returncode == 0, proc.stderr or proc.stdout
    seeded = re.search(r"(\d+) transactions", proc.stdout)
    assert seeded is not None
    assert int(seeded.group(1)) > 0

    async def _verify() -> None:
        engine = create_async_engine(db_url, poolclass=NullPool)
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as public:
                login = await LocalIdentityService(public).authenticate(
                    "demo@kaleta.app", "demo-kaleta"
                )
                assert login.email == "demo@kaleta.app"
        finally:
            await engine.dispose()

    asyncio.run(_verify())


def test_reset_demo_refuses_without_demo_flag(tmp_path: Path) -> None:
    proc = _reset_demo(fresh_database_url("reset_demo_refused"), tmp_path)
    assert proc.returncode == 1
    assert "KALETA_DEMO" in (proc.stderr or proc.stdout)
