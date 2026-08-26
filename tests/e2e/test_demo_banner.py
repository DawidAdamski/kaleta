# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E coverage for the demo-instance banner.

Covers: KAL-PLT-001
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from collections.abc import Generator
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import Page

from tests.e2e.conftest import E2E_PASSWORD, E2E_USERNAME, PROJECT_ROOT, _ensure_e2e_user, _run_alembic, _terminate_process, _wait_for_server, _write_kaleta_config, login

DEMO_PORT = 8082
DEMO_BASE = f"http://127.0.0.1:{DEMO_PORT}"


def _pump_stdout(proc: subprocess.Popen[str], log_path: Path) -> None:
    assert proc.stdout is not None
    with log_path.open("w", encoding="utf-8") as log_file:
        for line in proc.stdout:
            log_file.write(line)
            log_file.flush()


@pytest.fixture(scope="module")
def demo_e2e_server(tmp_path_factory: pytest.TempPathFactory) -> Generator[str]:
    home = tmp_path_factory.mktemp("demo_e2e_home")
    db_dir = tmp_path_factory.mktemp("demo_e2e_db")
    log_dir = tmp_path_factory.mktemp("demo_e2e_logs")
    db_path = db_dir / "demo-e2e.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    log_path = log_dir / "kaleta-demo-e2e-server.log"

    _write_kaleta_config(home, db_url)
    _run_alembic(db_url)

    env = os.environ.copy()
    env["HOME"] = str(home)
    env["KALETA_PORT"] = str(DEMO_PORT)
    env["KALETA_DEBUG"] = "true"
    env["KALETA_DEMO"] = "true"
    env["KALETA_DB_URL"] = db_url
    env["NICEGUI_SCREEN_TEST_PORT"] = str(DEMO_PORT)

    proc = subprocess.Popen(
        ["uv", "run", "kaleta"],
        cwd=PROJECT_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    pump = threading.Thread(target=_pump_stdout, args=(proc, log_path), daemon=True)
    pump.start()

    try:
        _wait_for_server(DEMO_BASE)
        _ensure_e2e_user(db_url)
        yield DEMO_BASE
    finally:
        _terminate_process(proc)
        pump.join(timeout=5)


@pytest.fixture
def demo_page(browser, demo_e2e_server: str):  # noqa: ANN001
    context = browser.new_context()
    page = context.new_page()
    login(page, demo_e2e_server)
    yield page
    context.close()


def test_demo_banner_visible_and_dismissible(demo_page: Page, demo_e2e_server: str) -> None:
    """Covers: KAL-PLT-001"""
    demo_page.goto(f"{demo_e2e_server}/")
    banner = demo_page.get_by_text("Demo instance — data resets daily.")
    banner.wait_for(state="visible", timeout=15000)

    demo_page.locator("button").filter(has=demo_page.locator(".material-icons", has_text="close")).first.click()
    banner.wait_for(state="hidden", timeout=5000)

    demo_page.goto(f"{demo_e2e_server}/transactions")
    expect_hidden = demo_page.get_by_text("Demo instance — data resets daily.")
    expect_hidden.wait_for(state="hidden", timeout=5000)
