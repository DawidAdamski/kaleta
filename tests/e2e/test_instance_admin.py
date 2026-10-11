# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E: the instance administrator's page on a self-hosted instance (ADR-38 §5).

One app on a fresh database, ``KALETA_AUTH_BACKEND=local``. The tests run in
file order and build on each other: the administrator sets the instance up,
creates a family, its owner signs in with the one-time password and must
replace it, the family is suspended, and registration is opened and closed.

Covers: KAL-ADM-007, KAL-ADM-008, KAL-ADM-009, KAL-ADM-010
"""

from __future__ import annotations

import os
import re
import subprocess
import threading
from collections.abc import Generator
from dataclasses import dataclass, field

import pytest
from playwright.sync_api import Browser, Page, expect

from tests.e2e.conftest import (
    PROJECT_ROOT,
    _pump_stdout_to_log,
    _terminate_process,
    _wait_for_server,
)
from tests.suite_database import fresh_database_url, query

# Its own port: 8081–8087 are taken by the other e2e servers.
ADMIN_PORT = 8088
BASE = f"http://127.0.0.1:{ADMIN_PORT}"

ADMIN = "admin@example.com"
ADMIN_PASSWORD = "correct-horse-battery"
JAN = "jan@example.com"
JAN_PASSWORD = "jan-chose-this-one"
PASSPHRASE = "our family data passphrase"
FAMILY = "Kowalscy"


@dataclass
class Instance:
    db_url: str
    #: What the tests learn on the way and hand to the next one.
    shared: dict[str, str] = field(default_factory=dict)

    def registry(self, sql: str) -> list[tuple[object, ...]]:
        return query(self.db_url, sql)


@pytest.fixture(scope="module")
def instance(tmp_path_factory: pytest.TempPathFactory) -> Generator[Instance]:
    home = tmp_path_factory.mktemp("admin_home")
    db_url = fresh_database_url("e2e_instance_admin")
    log_path = tmp_path_factory.mktemp("admin_logs") / "kaleta-admin.log"
    env = os.environ.copy()
    env.pop("KALETA_DB_URL", None)
    env.update(
        {
            "HOME": str(home),
            "KALETA_PORT": str(ADMIN_PORT),
            "KALETA_DEBUG": "true",
            "KALETA_DB_URL": db_url,
            "KALETA_AUTH_BACKEND": "local",
            "NICEGUI_SCREEN_TEST_PORT": str(ADMIN_PORT),
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
        _wait_for_server(BASE)
        yield Instance(db_url)
    finally:
        _terminate_process(proc)
        pump.join(timeout=5)


@pytest.fixture(scope="module")
def admin_page(instance: Instance, browser: Browser) -> Generator[Page]:
    """The administrator's browser, kept across the module's tests."""
    context = browser.new_context()
    page = context.new_page()
    yield page
    context.close()


@pytest.fixture
def fresh_page(browser: Browser) -> Generator[Page]:
    context = browser.new_context()
    page = context.new_page()
    yield page
    context.close()


def _set_passphrase(page: Page) -> None:
    expect(page).to_have_url(re.compile(r"/unlock"), timeout=15000)
    page.get_by_label("New data passphrase", exact=True).fill(PASSPHRASE)
    page.get_by_label("Repeat the passphrase", exact=True).fill(PASSPHRASE)
    page.get_by_role("button", name="Set passphrase").click()
    expect(page.get_by_test_id("recovery-code")).to_be_visible(timeout=20000)
    page.get_by_text("I have saved my recovery code").click()
    page.get_by_role("button", name="Continue").click()
    expect(page).not_to_have_url(re.compile(r"/unlock"), timeout=20000)


def _log_in(page: Page, email: str, password: str) -> None:
    page.goto(f"{BASE}/login")
    page.get_by_label("E-mail", exact=True).fill(email)
    page.get_by_label("Password", exact=True).fill(password)
    page.get_by_role("button", name="Log in").click()


def _step_up(page: Page) -> None:
    dialog = page.get_by_role("dialog")
    expect(dialog.get_by_text("Confirm it is you")).to_be_visible(timeout=10000)
    dialog.get_by_label("Password", exact=True).fill(ADMIN_PASSWORD)
    dialog.get_by_role("button", name="Confirm").click()


def test_the_administrator_has_the_page_in_the_navigation(
    instance: Instance, admin_page: Page
) -> None:
    """Covers: KAL-ADM-007"""
    page = admin_page
    page.goto(f"{BASE}/create-account")
    page.get_by_label("E-mail", exact=True).fill(ADMIN)
    page.get_by_label("Password", exact=True).fill(ADMIN_PASSWORD)
    page.get_by_label("Confirm password", exact=True).fill(ADMIN_PASSWORD)
    page.get_by_role("button", name="Sign up").click()
    _set_passphrase(page)

    page.goto(f"{BASE}/settings")
    page.locator(".k-drawer").get_by_text("Administration", exact=True).click()
    expect(page).to_have_url(f"{BASE}/admin", timeout=10000)
    expect(page.get_by_test_id("admin-families")).to_be_visible(timeout=10000)
    expect(page.get_by_test_id("admin-registration")).to_contain_text("Closed")


def test_a_new_familys_owner_must_replace_the_one_time_password(
    instance: Instance, admin_page: Page, fresh_page: Page
) -> None:
    """Covers: KAL-ADM-008, KAL-ADM-009"""
    page = admin_page
    page.goto(f"{BASE}/admin")
    page.get_by_role("button", name="New family").click()
    page.get_by_label("Family name", exact=True).fill(FAMILY)
    page.get_by_label("Owner's e-mail", exact=True).fill(JAN)
    page.get_by_role("button", name="Create", exact=True).click()
    _step_up(page)
    password = page.get_by_test_id("admin-one-time-password").inner_text(timeout=15000).strip()
    assert len(password) >= 12
    page.get_by_role("button", name="Close").click()
    families = page.get_by_test_id("admin-families")
    expect(families).to_contain_text(FAMILY, timeout=10000)
    expect(families).to_contain_text("pending")
    assert instance.registry(
        "SELECT must_change_password FROM local_identities WHERE email = 'jan@example.com'"
    ) == [(True,)]

    owner = fresh_page
    _log_in(owner, JAN, password)
    expect(owner).to_have_url(f"{BASE}/change-password", timeout=15000)
    owner.goto(f"{BASE}/transactions")
    expect(owner).to_have_url(f"{BASE}/change-password", timeout=10000)
    owner.get_by_label("New password", exact=True).fill(JAN_PASSWORD)
    owner.get_by_label("Confirm password", exact=True).fill(JAN_PASSWORD)
    owner.get_by_role("button", name="Save password").click()
    _set_passphrase(owner)

    # A member of another family: no Administration, and /admin is not there.
    expect(owner.locator(".k-drawer").get_by_text("Administration", exact=True)).to_have_count(0)
    response = owner.goto(f"{BASE}/admin")
    assert response is not None and response.status == 404
    assert instance.registry(
        "SELECT must_change_password FROM local_identities WHERE email = 'jan@example.com'"
    ) == [(False,)]
    instance.shared["jan_password"] = JAN_PASSWORD


def test_a_suspended_familys_owner_is_refused(
    instance: Instance, admin_page: Page, fresh_page: Page
) -> None:
    """Covers: KAL-ADM-008 — the step-up of the test before is still fresh."""
    page = admin_page
    page.goto(f"{BASE}/admin")
    tenant_id = instance.registry("SELECT id FROM tenants WHERE name = 'Kowalscy'")[0][0]
    row = page.get_by_test_id(f"admin-family-{tenant_id}")
    row.get_by_role("button", name="Suspend").click()
    expect(page.get_by_text("Confirm it is you")).to_have_count(0)
    expect(page.get_by_test_id(f"admin-family-{tenant_id}")).to_contain_text(
        "suspended", timeout=10000
    )

    _log_in(fresh_page, JAN, instance.shared["jan_password"])
    expect(fresh_page.get_by_text("This account is not available.")).to_be_visible(timeout=10000)
    expect(fresh_page).to_have_url(re.compile(r"/login"))
    audit = page.get_by_test_id("admin-audit")
    expect(audit).to_contain_text("Family suspended")
    expect(audit).to_contain_text(ADMIN)
    expect(audit).not_to_contain_text(JAN)


def test_closed_registration_shows_no_sign_up_link(
    instance: Instance, admin_page: Page, fresh_page: Page
) -> None:
    """Covers: KAL-ADM-010"""
    page = admin_page
    page.goto(f"{BASE}/admin")
    registration = page.get_by_test_id("admin-registration")
    registration.get_by_text("Open", exact=True).click()
    expect(registration).to_contain_text("Anyone who can reach this address", timeout=10000)
    fresh_page.goto(f"{BASE}/login")
    expect(fresh_page.get_by_role("link", name="Create an account")).to_be_visible(timeout=10000)

    page.get_by_test_id("admin-registration").get_by_text("Closed", exact=True).click()
    expect(page.get_by_test_id("admin-registration")).not_to_contain_text(
        "Anyone who can reach this address", timeout=10000
    )
    fresh_page.goto(f"{BASE}/login")
    expect(fresh_page.get_by_role("button", name="Log in")).to_be_visible(timeout=10000)
    expect(fresh_page.get_by_role("link", name="Create an account")).to_have_count(0)
