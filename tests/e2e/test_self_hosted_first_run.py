# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E: a self-hosted instance on the registry layout — the administrator's first run.

The app runs with ``KALETA_TENANCY=multi`` and ``KALETA_AUTH_BACKEND=local``
(ADR-38) on a multi-tenant SQLite database. Nothing exists yet: the login page
sends the first visitor to set up the administrator, whose first sign-in
provisions the first family; afterwards registration is closed.

Covers: KAL-TEN-015, KAL-TEN-016
"""

from __future__ import annotations

import os
import re
import sqlite3
import subprocess
import threading
from collections.abc import Generator
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Page, expect

from tests.e2e.conftest import (
    PROJECT_ROOT,
    _pump_stdout_to_log,
    _terminate_process,
    _wait_for_server,
)

# Its own port: 8081–8086 are taken by the other e2e servers.
SELF_HOSTED_PORT = 8087
SELF_HOSTED_BASE = f"http://127.0.0.1:{SELF_HOSTED_PORT}"

ADMIN = "admin@example.com"
PASSWORD = "correct-horse-battery"
DATA_PASSPHRASE = "our family data passphrase"


class SelfHostedInstance:
    def __init__(self, base: str, db_path: Path) -> None:
        self.base = base
        self.db_path = db_path

    def _registry(self, sql: str) -> list[tuple[object, ...]]:
        registry = self.db_path.with_name(f"{self.db_path.stem}.public.db")
        with sqlite3.connect(registry) as conn:
            return list(conn.execute(sql))

    def tenant_schemas(self) -> list[str]:
        return [str(row[0]) for row in self._registry("SELECT schema_name FROM tenants")]

    def admins(self) -> list[str]:
        return [
            str(row[0])
            for row in self._registry("SELECT email FROM local_identities WHERE is_instance_admin")
        ]


@pytest.fixture(scope="module")
def instance(tmp_path_factory: pytest.TempPathFactory) -> Generator[SelfHostedInstance]:
    home = tmp_path_factory.mktemp("self_hosted_home")
    db_path = tmp_path_factory.mktemp("self_hosted_db") / "family.db"
    log_path = tmp_path_factory.mktemp("self_hosted_logs") / "kaleta-self-hosted.log"

    env = os.environ.copy()
    env.pop("KALETA_DB_URL", None)
    env.update(
        {
            "HOME": str(home),
            "KALETA_PORT": str(SELF_HOSTED_PORT),
            "KALETA_DEBUG": "true",
            "KALETA_DB_URL": f"sqlite+aiosqlite:///{db_path}",
            "KALETA_TENANCY": "multi",
            "KALETA_AUTH_BACKEND": "local",
            "NICEGUI_SCREEN_TEST_PORT": str(SELF_HOSTED_PORT),
        }
    )
    proc = subprocess.Popen(
        ["uv", "run", "kaleta"],
        cwd=PROJECT_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    pump = threading.Thread(target=_pump_stdout_to_log, args=(proc, log_path), daemon=True)
    pump.start()
    try:
        _wait_for_server(SELF_HOSTED_BASE)
        yield SelfHostedInstance(SELF_HOSTED_BASE, db_path)
    finally:
        _terminate_process(proc)
        pump.join(timeout=5)


@pytest.fixture
def fresh_page(browser: Browser) -> Generator[Page]:
    context = browser.new_context()
    page = context.new_page()
    yield page
    context.close()


def test_the_first_visitor_sets_up_the_administrator_and_the_first_family(
    instance: SelfHostedInstance, fresh_page: Page
) -> None:
    """Covers: KAL-TEN-015"""
    page = fresh_page
    base = instance.base

    page.goto(f"{base}/")
    expect(page).to_have_url(f"{base}/create-account", timeout=10000)
    expect(page.get_by_text("Set up this Kaleta", exact=True)).to_be_visible(timeout=10000)

    page.get_by_label("E-mail", exact=True).fill(ADMIN)
    page.get_by_label("Password", exact=True).fill(PASSWORD)
    page.get_by_label("Confirm password", exact=True).fill(PASSWORD)
    page.get_by_role("button", name="Sign up").click()

    expect(page).to_have_url(re.compile(r"/unlock"), timeout=15000)
    page.get_by_label("New data passphrase", exact=True).fill(DATA_PASSPHRASE)
    page.get_by_label("Repeat the passphrase", exact=True).fill(DATA_PASSPHRASE)
    page.get_by_role("button", name="Set passphrase").click()
    expect(page.get_by_test_id("recovery-code")).to_be_visible(timeout=20000)
    page.get_by_text("I have saved my recovery code").click()
    page.get_by_role("button", name="Continue").click()
    expect(page).not_to_have_url(re.compile(r"/unlock"), timeout=20000)

    assert instance.admins() == [ADMIN]
    schemas = instance.tenant_schemas()
    assert len(schemas) == 1
    assert schemas[0].startswith("t_")


def test_afterwards_registration_is_closed(instance: SelfHostedInstance, fresh_page: Page) -> None:
    """Covers: KAL-TEN-016 — runs after the first-run test in this module."""
    assert instance.admins() == [ADMIN]
    page = fresh_page
    base = instance.base

    page.goto(f"{base}/login")
    expect(page.get_by_role("button", name="Log in")).to_be_visible(timeout=10000)
    expect(page.get_by_role("link", name="Create an account")).to_have_count(0)

    page.goto(f"{base}/create-account")
    expect(page).to_have_url(re.compile(r"/login"), timeout=10000)
