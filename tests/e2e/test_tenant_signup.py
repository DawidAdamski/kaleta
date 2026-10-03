# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E: a hosted instance — sign up, confirm the e-mail, first login provisions.

The app runs with ``KALETA_TENANCY=multi`` and ``KALETA_AUTH_BACKEND=supabase``
against ``tests.fake_gotrue`` (a local stand-in for Supabase Auth whose
verification link the test reads instead of a mailbox), on a multi-tenant
SQLite database — each tenant schema a file of its own.

Covers: KAL-TEN-001, KAL-TEN-005, KAL-TEN-006, KAL-TEN-007, KAL-TEN-009,
KAL-TEN-012
"""

from __future__ import annotations

import os
import re
import sqlite3
import subprocess
import threading
from collections.abc import Generator
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import Browser, Page, expect

from tests.e2e.conftest import (
    PROJECT_ROOT,
    _pump_stdout_to_log,
    _terminate_process,
    _wait_for_server,
)
from tests.fake_gotrue import SERVICE_ROLE_KEY, FakeGoTrueServer

# Their own ports: 8081–8084 are taken by the other e2e servers.
HOSTED_PORT = 8085
HOSTED_BASE = f"http://127.0.0.1:{HOSTED_PORT}"
GOTRUE_PORT = 8086

#: Any /login URL, query string or not: the page starts on one with a query.
_ON_LOGIN = re.compile(r"/login(\?|$)")

EMAIL = "ania@example.com"
PASSWORD = "correct-horse-battery"


class HostedInstance:
    def __init__(self, base: str, db_path: Path, gotrue: FakeGoTrueServer) -> None:
        self.base = base
        self.db_path = db_path
        self.gotrue = gotrue

    def tenant_schemas(self) -> list[str]:
        registry = self.db_path.with_name(f"{self.db_path.stem}.public.db")
        with sqlite3.connect(registry) as conn:
            return [row[0] for row in conn.execute("SELECT schema_name FROM tenants")]

    def schema_files(self) -> list[Path]:
        return sorted(self.db_path.parent.glob(f"{self.db_path.stem}.t_*.db"))


@pytest.fixture(scope="module")
def hosted(tmp_path_factory: pytest.TempPathFactory) -> Generator[HostedInstance]:
    home = tmp_path_factory.mktemp("hosted_home")
    db_path = tmp_path_factory.mktemp("hosted_db") / "hosted.db"
    log_path = tmp_path_factory.mktemp("hosted_logs") / "kaleta-hosted.log"

    with FakeGoTrueServer(GOTRUE_PORT) as gotrue:
        env = os.environ.copy()
        env.update(
            {
                "HOME": str(home),
                "KALETA_PORT": str(HOSTED_PORT),
                "KALETA_DEBUG": "true",
                "KALETA_DB_URL": f"sqlite+aiosqlite:///{db_path}",
                "KALETA_TENANCY": "multi",
                "KALETA_AUTH_BACKEND": "supabase",
                "KALETA_SUPABASE_URL": gotrue.base_url,
                "KALETA_SUPABASE_ANON_KEY": "anon-e2e",
                "KALETA_SUPABASE_SERVICE_ROLE_KEY": SERVICE_ROLE_KEY,
                "KALETA_PUBLIC_URL": HOSTED_BASE,
                "NICEGUI_SCREEN_TEST_PORT": str(HOSTED_PORT),
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
            _wait_for_server(HOSTED_BASE)
            yield HostedInstance(HOSTED_BASE, db_path, gotrue)
        finally:
            _terminate_process(proc)
            pump.join(timeout=5)


@pytest.fixture
def fresh_page(browser: Browser) -> Generator[Page]:
    context = browser.new_context()
    page = context.new_page()
    yield page
    context.close()


def _log_in(page: Page, base: str) -> None:
    _log_in_as(page, base, EMAIL, PASSWORD)


#: A hosted account always encrypts (hosted-field-encryption): the first
#: sign-in chooses this, every later one types it on /unlock.
DATA_PASSPHRASE = "our hosted data passphrase"


def _choose_data_passphrase(page: Page) -> None:
    """Sign-up step 2 — the data passphrase and its recovery code (KAL-ENC-002)."""
    expect(page).to_have_url(re.compile(r"/unlock"), timeout=15000)
    page.get_by_label("New data passphrase", exact=True).fill(DATA_PASSPHRASE)
    page.get_by_label("Repeat the passphrase", exact=True).fill(DATA_PASSPHRASE)
    page.get_by_role("button", name="Set passphrase").click()
    expect(page.get_by_test_id("recovery-code")).to_be_visible(timeout=20000)
    page.get_by_text("I have saved my recovery code").click()
    page.get_by_role("button", name="Continue").click()
    expect(page).not_to_have_url(re.compile(r"/unlock"), timeout=20000)


def _unlock(page: Page) -> None:
    expect(page).to_have_url(re.compile(r"/unlock"), timeout=15000)
    page.get_by_label("Data passphrase", exact=True).fill(DATA_PASSPHRASE)
    page.get_by_role("button", name="Unlock", exact=True).click()
    expect(page).not_to_have_url(re.compile(r"/unlock"), timeout=20000)


def _log_in_as(page: Page, base: str, email: str, password: str) -> None:
    page.goto(f"{base}/login")
    page.get_by_label("E-mail", exact=True).fill(email)
    page.get_by_label("Password", exact=True).fill(password)
    page.get_by_role("button", name="Log in").click()


def test_sign_up_verify_and_first_login_provisions_an_account(
    hosted: HostedInstance, fresh_page: Page
) -> None:
    """Covers: KAL-TEN-001"""
    page = fresh_page
    base = hosted.base

    # A hosted login page has no first-user bootstrap: it is just a login.
    page.goto(f"{base}/")
    expect(page).to_have_url(f"{base}/login?redirect_to=/", timeout=10000)
    page.get_by_role("link", name="Create an account").click()

    page.get_by_label("E-mail", exact=True).fill(EMAIL)
    page.get_by_label("Password", exact=True).fill(PASSWORD)
    page.get_by_label("Confirm password", exact=True).fill(PASSWORD)
    page.get_by_role("button", name="Sign up").click()
    expect(page.get_by_text("Check your inbox", exact=True)).to_be_visible(timeout=10000)
    # Nothing is provisioned for an address nobody has confirmed.
    assert hosted.tenant_schemas() == []

    _log_in(page, base)
    expect(page.get_by_text("Confirm your e-mail address first", exact=False)).to_be_visible(
        timeout=10000
    )
    assert hosted.tenant_schemas() == []

    link = httpx.get(f"{hosted.gotrue.base_url}/_test/inbox", params={"email": EMAIL}).json()
    page.goto(link["link"])
    expect(page).to_have_url(f"{base}/login?reason=verified", timeout=10000)
    expect(page.get_by_text("Your e-mail address is confirmed.", exact=False)).to_be_visible(
        timeout=10000
    )

    page.get_by_label("E-mail", exact=True).fill(EMAIL)
    page.get_by_label("Password", exact=True).fill(PASSWORD)
    page.get_by_role("button", name="Log in").click()
    expect(page).not_to_have_url(_ON_LOGIN, timeout=15000)
    _choose_data_passphrase(page)
    page.goto(f"{base}/")
    expect(page.get_by_text("Dashboard", exact=True).first).to_be_visible(timeout=15000)

    schemas = hosted.tenant_schemas()
    assert len(schemas) == 1
    assert schemas[0].startswith("t_")
    assert "ania" not in schemas[0]
    assert [p.name for p in hosted.schema_files()] == [f"hosted.{schemas[0]}.db"]


def test_signing_in_again_reuses_the_account(hosted: HostedInstance, fresh_page: Page) -> None:
    """Covers: KAL-TEN-001, KAL-TEN-012 — provisioning happens once; the next login finds it."""
    before = hosted.tenant_schemas()
    assert len(before) == 1, "runs after the sign-up test in this module"

    _log_in(fresh_page, hosted.base)
    expect(fresh_page).not_to_have_url(_ON_LOGIN, timeout=15000)
    # KAL-TEN-012: the page that asks again says why it asks again.
    expect(fresh_page.get_by_test_id("unlock-restart-note")).to_contain_text(
        "the server restarts", timeout=15000
    )
    _unlock(fresh_page)
    fresh_page.goto(f"{hosted.base}/")
    expect(fresh_page.get_by_text("Dashboard", exact=True).first).to_be_visible(timeout=15000)

    assert hosted.tenant_schemas() == before


def test_forgotten_password_is_reset_through_an_emailed_link(
    hosted: HostedInstance, fresh_page: Page
) -> None:
    """Covers: KAL-TEN-005"""
    assert hosted.tenant_schemas(), "runs after the sign-up test in this module"
    page = fresh_page
    base = hosted.base
    new_password = "a-brand-new-passphrase"

    page.goto(f"{base}/login")
    page.get_by_role("link", name="Forgot password?").click()
    expect(page).to_have_url(f"{base}/reset-password", timeout=10000)
    page.get_by_label("E-mail", exact=True).fill(EMAIL)
    page.get_by_role("button", name="Send link").click()
    expect(
        page.get_by_text("a link to reset the password is on its way", exact=False)
    ).to_be_visible(timeout=10000)

    link = httpx.get(f"{hosted.gotrue.base_url}/_test/inbox", params={"email": EMAIL}).json()
    assert link["link"].startswith(f"{base}/reset-password?token_hash=")
    page.goto(link["link"])
    page.get_by_label("Password", exact=True).fill(new_password)
    page.get_by_label("Confirm password", exact=True).fill(new_password)
    page.get_by_role("button", name="Save password").click()
    expect(page).to_have_url(f"{base}/login?reason=password_reset", timeout=10000)
    expect(page.get_by_text("Your password was changed.", exact=False)).to_be_visible(timeout=10000)

    page.get_by_label("E-mail", exact=True).fill(EMAIL)
    page.get_by_label("Password", exact=True).fill(PASSWORD)
    page.get_by_role("button", name="Log in").click()
    expect(page.get_by_text("Invalid e-mail or password.")).to_be_visible(timeout=10000)

    page.get_by_label("Password", exact=True).fill(new_password)
    page.get_by_role("button", name="Log in").click()
    expect(page).not_to_have_url(_ON_LOGIN, timeout=15000)
    # Same account as before: the reset changed a password, not an identity.
    assert len(hosted.tenant_schemas()) == 1


def _inbox(hosted: HostedInstance, email: str) -> str:
    answer = httpx.get(f"{hosted.gotrue.base_url}/_test/inbox", params={"email": email})
    return str(answer.json()["link"])


def test_a_lost_confirmation_is_sent_again(hosted: HostedInstance, fresh_page: Page) -> None:
    """Covers: KAL-TEN-006"""
    page = fresh_page
    base = hosted.base
    address = "jan@example.com"
    accounts_before = len(hosted.tenant_schemas())

    page.goto(f"{base}/create-account")
    page.get_by_label("E-mail", exact=True).fill(address)
    page.get_by_label("Password", exact=True).fill(PASSWORD)
    page.get_by_label("Confirm password", exact=True).fill(PASSWORD)
    page.get_by_role("button", name="Sign up").click()
    expect(page.get_by_text("Check your inbox", exact=True)).to_be_visible(timeout=10000)
    lost = _inbox(hosted, address)
    assert hosted.gotrue.gotrue.sent[(address, "signup")] == 1

    page.get_by_role("button", name="Resend confirmation e-mail").click()
    expect(page.get_by_text("A new link is on its way", exact=False)).to_be_visible(timeout=10000)
    assert hosted.gotrue.gotrue.sent[(address, "signup")] == 2
    fresh = _inbox(hosted, address)
    assert fresh != lost

    # The login page offers the same, once the password proves to be right —
    # and within the minute it sends nothing more, while saying the same.
    _log_in_as(page, base, address, PASSWORD)
    expect(page.get_by_text("Confirm your e-mail address first", exact=False)).to_be_visible(
        timeout=10000
    )
    page.get_by_role("button", name="Resend confirmation e-mail").click()
    expect(page.get_by_text("A new link is on its way", exact=False)).to_be_visible(timeout=10000)
    assert hosted.gotrue.gotrue.sent[(address, "signup")] == 2

    # The superseded link no longer confirms; the new one does.
    refused = page.goto(lost)
    assert refused is not None
    assert refused.status == 403
    page.goto(fresh)
    expect(page).to_have_url(f"{base}/login?reason=verified", timeout=10000)

    _log_in_as(page, base, address, PASSWORD)
    expect(page).not_to_have_url(_ON_LOGIN, timeout=15000)
    assert len(hosted.tenant_schemas()) == accounts_before + 1


def test_a_magic_link_signs_in_to_an_existing_account(
    hosted: HostedInstance, fresh_page: Page
) -> None:
    """Covers: KAL-TEN-007"""
    page = fresh_page
    base = hosted.base
    accounts_before = hosted.tenant_schemas()
    assert accounts_before, "runs after the sign-up test in this module"

    page.goto(f"{base}/login")
    page.get_by_label("E-mail", exact=True).fill(EMAIL)
    page.get_by_role("button", name="E-mail me a sign-in link").click()
    expect(
        page.get_by_text("If an account uses this address, a sign-in link is on its way.")
    ).to_be_visible(timeout=10000)
    link = _inbox(hosted, EMAIL)
    assert link.startswith(f"{base}/auth/magic?token_hash=")

    page.goto(link)
    expect(page).not_to_have_url(_ON_LOGIN, timeout=15000)
    _unlock(page)
    page.goto(f"{base}/")
    expect(page.get_by_text("Dashboard", exact=True).first).to_be_visible(timeout=15000)
    # The same account as the password signs in to; nothing new provisioned.
    assert hosted.tenant_schemas() == accounts_before


def test_a_magic_link_creates_no_account(hosted: HostedInstance, fresh_page: Page) -> None:
    """Covers: KAL-TEN-007 — an unknown address hears the same, and gets nothing."""
    page = fresh_page
    page.goto(f"{hosted.base}/login")
    page.get_by_label("E-mail", exact=True).fill("nobody@example.com")
    page.get_by_role("button", name="E-mail me a sign-in link").click()
    expect(
        page.get_by_text("If an account uses this address, a sign-in link is on its way.")
    ).to_be_visible(timeout=10000)
    assert ("nobody@example.com", "magiclink") not in hosted.gotrue.gotrue.sent
    assert "nobody@example.com" not in hosted.gotrue.gotrue.users


def test_a_used_magic_link_is_refused(hosted: HostedInstance, fresh_page: Page) -> None:
    """Covers: KAL-TEN-007 — a link works once; after that it is expired."""
    page = fresh_page
    base = hosted.base
    used = _inbox(hosted, EMAIL)
    assert used.startswith(f"{base}/auth/magic?token_hash="), "runs after the magic-link test"

    page.goto(used)
    expect(page).to_have_url(f"{base}/login?reason=link_expired", timeout=10000)
    expect(page.get_by_text("That sign-in link is invalid or has expired.")).to_be_visible(
        timeout=10000
    )


def test_the_owner_deletes_the_account_from_settings(
    hosted: HostedInstance, fresh_page: Page
) -> None:
    """Covers: KAL-TEN-009"""
    page = fresh_page
    base = hosted.base
    address = "leaving@example.com"

    page.goto(f"{base}/create-account")
    page.get_by_label("E-mail", exact=True).fill(address)
    page.get_by_label("Password", exact=True).fill(PASSWORD)
    page.get_by_label("Confirm password", exact=True).fill(PASSWORD)
    page.get_by_role("button", name="Sign up").click()
    expect(page.get_by_text("Check your inbox", exact=True)).to_be_visible(timeout=10000)
    page.goto(_inbox(hosted, address))
    expect(page).to_have_url(f"{base}/login?reason=verified", timeout=10000)
    schemas_before = set(hosted.tenant_schemas())
    _log_in_as(page, base, address, PASSWORD)
    expect(page).not_to_have_url(_ON_LOGIN, timeout=15000)
    _choose_data_passphrase(page)
    (mine,) = set(hosted.tenant_schemas()) - schemas_before

    page.goto(f"{base}/settings")
    page.get_by_role("tab", name="Data").click()
    page.get_by_role("button", name="Delete my account").click()
    members = page.get_by_test_id("delete-account-members")
    expect(members).to_contain_text(f"{address} · owner", timeout=10000)
    page.get_by_role("button", name="Continue").click()

    # A wrong passphrase deletes nothing.
    page.get_by_label("Data passphrase", exact=True).fill("not my passphrase")
    page.get_by_role("button", name="Delete for good").click()
    expect(page.get_by_text("That passphrase does not unlock your data.")).to_be_visible(
        timeout=15000
    )
    assert mine in hosted.tenant_schemas()

    page.get_by_label("Data passphrase", exact=True).fill(DATA_PASSPHRASE)
    page.get_by_role("button", name="Delete for good").click()
    expect(page).to_have_url(_ON_LOGIN, timeout=20000)

    assert mine not in hosted.tenant_schemas()
    assert not any(mine in p.name for p in hosted.schema_files())
    assert address not in hosted.gotrue.gotrue.users
    _log_in_as(page, base, address, PASSWORD)
    expect(page.get_by_text("Invalid e-mail or password.")).to_be_visible(timeout=10000)
