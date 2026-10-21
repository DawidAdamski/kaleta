# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E: two people, one household — invite, join, approve, share, remove.

One app of its own on a fresh database, ``local`` logins and encryption on (the
production setting). Two browser contexts, kept across the module's tests,
which run in file order and build on each other as the two people would: the
owner sets the instance up and invites, the partner joins through the link and
waits, the owner approves, both see the same payees — and the owner's pages say which of them
did what — the owner removes the partner and the partner is locked out.

Covers: KAL-HHS-013, KAL-HHS-014, KAL-HHS-015, KAL-HHS-016, KAL-HHS-018
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

from tests.e2e._ports import pick_free_port
from tests.e2e.conftest import (
    PROJECT_ROOT,
    _pump_stdout_to_log,
    _terminate_process,
    _wait_for_server,
)
from tests.suite_database import fresh_database_url, query

# A free port per pytest process (tests/e2e/_ports.py).
HOUSEHOLD_PORT = pick_free_port()
BASE = f"http://127.0.0.1:{HOUSEHOLD_PORT}"

# Literals from the KAL-HHS scenarios.
OWNER = "jan@example.com"
OWNER_PASSWORD = "jan-chose-this-one"
OWNER_PASSPHRASE = "our household passphrase"
PARTNER = "ania@example.com"
PARTNER_PASSWORD = "ania-chose-this-one"
PARTNER_PASSPHRASE = "ania's own long passphrase"


@dataclass
class Household:
    db_url: str
    #: What the tests learn on the way and hand to the next one.
    shared: dict[str, str] = field(default_factory=dict)

    def registry(self, sql: str) -> list[tuple[object, ...]]:
        return query(self.db_url, sql)


@pytest.fixture(scope="module")
def household(tmp_path_factory: pytest.TempPathFactory) -> Generator[Household]:
    home = tmp_path_factory.mktemp("household_home")
    db_url = fresh_database_url("e2e_household")
    log_path = tmp_path_factory.mktemp("household_logs") / "kaleta-household.log"
    env = os.environ.copy()
    env.pop("KALETA_DB_URL", None)
    env.update(
        {
            "HOME": str(home),
            "KALETA_PORT": str(HOUSEHOLD_PORT),
            "KALETA_DEBUG": "true",
            "KALETA_DB_URL": db_url,
            "KALETA_AUTH_BACKEND": "local",
            "KALETA_ENCRYPTION": "passphrase",
            "NICEGUI_SCREEN_TEST_PORT": str(HOUSEHOLD_PORT),
        }
    )
    env.pop("NICEGUI_STORAGE_PATH", None)
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
        yield Household(db_url)
    finally:
        _terminate_process(proc)
        pump.join(timeout=5)


def _context_page(browser: Browser) -> Generator[Page]:
    context = browser.new_context()
    page = context.new_page()
    yield page
    context.close()


@pytest.fixture(scope="module")
def owner_page(household: Household, browser: Browser) -> Generator[Page]:
    yield from _context_page(browser)


@pytest.fixture(scope="module")
def partner_page(household: Household, browser: Browser) -> Generator[Page]:
    yield from _context_page(browser)


@pytest.fixture
def fresh_page(browser: Browser) -> Generator[Page]:
    yield from _context_page(browser)


def _set_passphrase(page: Page, passphrase: str) -> None:
    expect(page).to_have_url(re.compile(r"/unlock"), timeout=15000)
    page.get_by_label("New data passphrase", exact=True).fill(passphrase)
    page.get_by_label("Repeat the passphrase", exact=True).fill(passphrase)
    page.get_by_role("button", name="Set passphrase").click()
    expect(page.get_by_test_id("recovery-code")).to_be_visible(timeout=20000)
    page.get_by_text("I have saved my recovery code").click()
    page.get_by_role("button", name="Continue").click()


def _add_payee(page: Page, name: str) -> None:
    page.goto(f"{BASE}/payees")
    page.get_by_role("button", name="Add Payee").click()
    dialog = page.get_by_role("dialog")
    dialog.get_by_label("Payee name", exact=True).fill(name)
    dialog.get_by_role("button", name="Save").click()
    expect(page.get_by_text("Payee created.")).to_be_visible(timeout=10000)


def _sees_payees(page: Page, *names: str) -> None:
    page.goto(f"{BASE}/payees")
    for name in names:
        expect(page.get_by_text(name, exact=True).first).to_be_visible(timeout=15000)


def _household_tab(page: Page) -> None:
    page.goto(f"{BASE}/settings?tab=household")
    expect(page.get_by_text("Members", exact=True)).to_be_visible(timeout=15000)


def test_the_owner_invites_and_the_partner_joins_and_waits(
    household: Household, owner_page: Page, partner_page: Page
) -> None:
    """Covers: KAL-HHS-013"""
    owner = owner_page
    owner.goto(f"{BASE}/create-account")
    owner.get_by_label("E-mail", exact=True).fill(OWNER)
    owner.get_by_label("Password", exact=True).fill(OWNER_PASSWORD)
    owner.get_by_label("Confirm password", exact=True).fill(OWNER_PASSWORD)
    owner.get_by_role("button", name="Sign up").click()
    _set_passphrase(owner, OWNER_PASSPHRASE)
    expect(owner).not_to_have_url(re.compile(r"/unlock"), timeout=20000)
    _add_payee(owner, "Biedronka")
    # A family of one: the ledger has no "Added by" to filter on.
    owner.goto(f"{BASE}/transactions")
    expect(owner.get_by_text("Transactions", exact=True).first).to_be_visible(timeout=15000)
    expect(owner.locator(".k-chip-members")).to_have_count(0)

    _household_tab(owner)
    owner.get_by_label("E-mail", exact=True).fill(PARTNER)
    owner.get_by_role("button", name="Invite").click()
    link = owner.get_by_test_id("invite-link").inner_text(timeout=10000).strip()
    assert re.fullmatch(rf"{re.escape(BASE)}/join\?token=[\w-]+", link)
    owner.get_by_role("dialog").get_by_role("button", name="Close").click()
    expect(owner.get_by_text("Open invitations")).to_be_visible()
    household.shared["link"] = link

    partner = partner_page
    partner.goto(link)
    expect(partner.get_by_test_id("join-email")).to_have_text(PARTNER, timeout=15000)
    partner.get_by_label("Password", exact=True).fill(PARTNER_PASSWORD)
    partner.get_by_label("Confirm password", exact=True).fill(PARTNER_PASSWORD)
    partner.get_by_role("button", name="Join").click()
    _set_passphrase(partner, PARTNER_PASSPHRASE)

    expect(partner.get_by_test_id("waiting-for")).to_have_text(
        f"Waiting for {OWNER} to approve you.", timeout=20000
    )
    fingerprint = partner.get_by_test_id("my-fingerprint").inner_text().strip()
    assert re.fullmatch(r"[0-9a-f]{4}( [0-9a-f]{4}){7}", fingerprint)
    household.shared["fingerprint"] = fingerprint
    # Waiting means no data: every page sends them back here.
    partner.goto(f"{BASE}/payees")
    expect(partner).to_have_url(re.compile(r"/unlock"), timeout=15000)
    assert household.registry(f"SELECT status FROM tenant_members WHERE email = '{PARTNER}'") == [
        ("pending",)
    ]


def test_a_used_invitation_link_no_longer_works(household: Household, fresh_page: Page) -> None:
    """Covers: KAL-HHS-014"""
    fresh_page.goto(household.shared["link"])
    expect(fresh_page.get_by_text("This invitation no longer works")).to_be_visible(timeout=15000)
    expect(fresh_page.get_by_test_id("join-email")).to_have_count(0)


def test_the_owner_approves_and_both_share_the_payees(
    household: Household, owner_page: Page, partner_page: Page
) -> None:
    """Covers: KAL-HHS-013, KAL-HHS-015, KAL-HHS-016, KAL-HHS-018"""
    owner = owner_page
    _household_tab(owner)
    row = owner.get_by_test_id(f"member-{PARTNER}")
    expect(row.get_by_test_id(f"fingerprint-{PARTNER}")).to_have_text(
        household.shared["fingerprint"]
    )
    row.get_by_role("button", name="Approve").click()
    dialog = owner.get_by_role("dialog")
    expect(dialog.get_by_text(household.shared["fingerprint"])).to_be_visible()
    dialog.get_by_label("Data passphrase", exact=True).fill(OWNER_PASSPHRASE)
    dialog.get_by_role("button", name="Approve").click()
    expect(owner.get_by_text(f"{PARTNER} is now a member.")).to_be_visible(timeout=15000)

    partner = partner_page
    partner.get_by_role("button", name="Check again").click()
    partner.get_by_label("Data passphrase", exact=True).fill(PARTNER_PASSPHRASE)
    partner.get_by_role("button", name="Unlock", exact=True).click()
    expect(partner).not_to_have_url(re.compile(r"/unlock"), timeout=20000)
    _sees_payees(partner, "Biedronka")
    _add_payee(partner, "Lidl")

    _sees_payees(owner, "Biedronka", "Lidl")

    # Two of them now: the owner's pages say who did what.
    owner.goto(f"{BASE}/settings?tab=history")
    who = owner.locator('[data-testid^="audit-who-"]')
    expect(who.filter(has_text=re.compile(r"^ania$")).first).to_be_visible(timeout=15000)
    expect(who.filter(has_text=re.compile(r"^jan$")).first).to_be_visible()
    owner.goto(f"{BASE}/transactions")
    expect(owner.locator(".k-chip-members")).to_be_visible(timeout=15000)
    owner.goto(f"{BASE}/wizard")
    expect(owner.get_by_test_id("wizard-household")).to_have_text(
        "Shared with your household: a step one of you completes is done for everyone.",
        timeout=15000,
    )


def test_removing_the_partner_locks_them_out(
    household: Household, owner_page: Page, partner_page: Page
) -> None:
    """Covers: KAL-HHS-013"""
    owner = owner_page
    _household_tab(owner)
    owner.get_by_test_id(f"member-{PARTNER}").get_by_role("button", name="Remove").click()
    dialog = owner.get_by_role("dialog")
    expect(dialog.get_by_text("Re-key the household (recommended)")).to_be_visible()
    dialog.get_by_role("button", name="Remove").click()
    expect(owner.get_by_text(f"{PARTNER} was removed.")).to_be_visible(timeout=30000)
    assert household.registry("SELECT key_version FROM tenants") == [(2,)]

    partner = partner_page
    partner.goto(f"{BASE}/payees")
    expect(partner).to_have_url(re.compile(r"/login"), timeout=15000)
    partner.get_by_label("E-mail", exact=True).fill(PARTNER)
    partner.get_by_label("Password", exact=True).fill(PARTNER_PASSWORD)
    partner.get_by_role("button", name="Log in").click()
    expect(partner.get_by_text("You are no longer a member of this household.")).to_be_visible(
        timeout=15000
    )

    # The owner's unlock moved to the new key with them.
    _sees_payees(owner, "Biedronka", "Lidl")
