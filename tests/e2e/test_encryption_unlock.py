# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E: the data passphrase, on an app of its own with encryption on (the default).

One app of its own (port 8083), one user, and the scenarios in the order a
person meets them: choose the passphrase at the first sign-in, unlock after
the next one, get it wrong, lock, recover with the code, change it, read the
privacy statement. Later tests build on the state earlier ones leave
(``_state``), as the person would.

Covers: KAL-ENC-002, KAL-ENC-003, KAL-ENC-004, KAL-ENC-005, KAL-ENC-006, KAL-ENC-007,
KAL-ENC-008
"""

from __future__ import annotations

import os
import re
import subprocess
import threading
from collections.abc import Generator

import pytest
from playwright.sync_api import Browser, Page, expect

from tests.e2e.conftest import (
    E2E_APP_ENV,
    PROJECT_ROOT,
    _pump_stdout_to_log,
    _terminate_process,
    _wait_for_server,
    login,
    prepare_e2e_database,
)
from tests.suite_database import fresh_database_url

ENC_PORT = 8083
ENC_BASE = f"http://127.0.0.1:{ENC_PORT}"

# Literals from the KAL-ENC scenarios.
FIRST_PASSPHRASE = "our household passphrase"
SECOND_PASSPHRASE = "a brand new passphrase"
THIRD_PASSPHRASE = "the changed passphrase"
SHORT_PASSPHRASE = "too short"

#: What the scenarios leave behind for the next one: the current passphrase
#: and the recovery code last shown.
_state: dict[str, str] = {}


@pytest.fixture(scope="module")
def encrypted_server(tmp_path_factory: pytest.TempPathFactory) -> Generator[str]:
    home = tmp_path_factory.mktemp("enc_e2e_home")
    log_dir = tmp_path_factory.mktemp("enc_e2e_logs")
    db_url = fresh_database_url("e2e_encryption")
    log_path = log_dir / "kaleta-enc-e2e-server.log"

    prepare_e2e_database(db_url)

    env = os.environ.copy()
    env.update(E2E_APP_ENV)
    env["HOME"] = str(home)
    env["KALETA_PORT"] = str(ENC_PORT)
    env["KALETA_DB_URL"] = db_url
    env["KALETA_ENCRYPTION"] = "passphrase"
    env["NICEGUI_SCREEN_TEST_PORT"] = str(ENC_PORT)

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
        _wait_for_server(ENC_BASE)
        yield ENC_BASE
    finally:
        _terminate_process(proc)
        pump.join(timeout=5)


@pytest.fixture
def fresh_page(browser: Browser, encrypted_server: str) -> Generator[Page]:
    """A new browser — signed in, so on its way to /unlock."""
    context = browser.new_context()
    page = context.new_page()
    login(page, encrypted_server)
    yield page
    context.close()


def _on_unlock(page: Page) -> None:
    page.wait_for_url(re.compile(r"/unlock"), timeout=15000)


def _left_unlock(page: Page) -> None:
    page.wait_for_url(lambda url: "/unlock" not in url, timeout=20000)


def _acknowledge_recovery_code(page: Page) -> str:
    code = page.get_by_test_id("recovery-code")
    expect(code).to_be_visible(timeout=20000)
    text = code.inner_text().strip()
    cont = page.get_by_role("button", name="Continue")
    expect(cont).to_be_disabled()
    page.get_by_text("I have saved my recovery code").click()
    expect(cont).to_be_enabled()
    cont.click()
    return text


def _unlock(page: Page, passphrase: str) -> None:
    _on_unlock(page)
    page.get_by_label("Data passphrase", exact=True).fill(passphrase)
    page.get_by_role("button", name="Unlock", exact=True).click()


def test_choosing_the_passphrase_at_the_first_sign_in(fresh_page: Page) -> None:
    """Covers: KAL-ENC-002"""
    page = fresh_page
    _on_unlock(page)
    expect(page.get_by_text("Choose a data passphrase")).to_be_visible()

    page.get_by_label("New data passphrase", exact=True).fill(SHORT_PASSPHRASE)
    page.get_by_label("Repeat the passphrase", exact=True).fill(SHORT_PASSPHRASE)
    page.get_by_role("button", name="Set passphrase").click()
    expect(page.get_by_text("Choose a passphrase of at least 12 characters.")).to_be_visible()

    page.get_by_label("New data passphrase", exact=True).fill(FIRST_PASSPHRASE)
    page.get_by_label("Repeat the passphrase", exact=True).fill(FIRST_PASSPHRASE)
    page.get_by_role("button", name="Set passphrase").click()

    _state["code"] = _acknowledge_recovery_code(page)
    _state["passphrase"] = FIRST_PASSPHRASE
    _left_unlock(page)
    assert re.fullmatch(r"[0-9A-Z]{5}(-[0-9A-Z]{1,5}){5}", _state["code"])


def test_a_wrong_passphrase_does_not_unlock(fresh_page: Page) -> None:
    """Covers: KAL-ENC-004"""
    _unlock(fresh_page, "not the passphrase at all")
    expect(fresh_page.get_by_text("That passphrase does not unlock your data.")).to_be_visible()
    assert "/unlock" in fresh_page.url


def test_unlocking_after_signing_in_again(fresh_page: Page) -> None:
    """Covers: KAL-ENC-003"""
    _unlock(fresh_page, _state["passphrase"])
    _left_unlock(fresh_page)


def test_lock_now_asks_for_the_passphrase_again(fresh_page: Page, encrypted_server: str) -> None:
    """Covers: KAL-ENC-007"""
    _unlock(fresh_page, _state["passphrase"])
    _left_unlock(fresh_page)
    fresh_page.goto(f"{encrypted_server}/settings?tab=security")
    fresh_page.get_by_role("button", name="Lock now").click()
    _on_unlock(fresh_page)

    fresh_page.goto(f"{encrypted_server}/transactions")
    _on_unlock(fresh_page)


def test_recovering_with_the_recovery_code(fresh_page: Page) -> None:
    """Covers: KAL-ENC-005"""
    page = fresh_page
    _on_unlock(page)
    page.get_by_role("button", name="Forgot it? Use your recovery code").click()
    page.get_by_label("Recovery code", exact=True).fill(_state["code"].lower())
    page.get_by_label("New data passphrase", exact=True).fill(SECOND_PASSPHRASE)
    page.get_by_label("Repeat the passphrase", exact=True).fill(SECOND_PASSPHRASE)
    page.get_by_role("button", name="Set new passphrase").click()

    fresh = _acknowledge_recovery_code(page)
    _left_unlock(page)
    assert fresh != _state["code"]
    _state.update(code=fresh, passphrase=SECOND_PASSPHRASE)


def test_changing_the_passphrase(fresh_page: Page, encrypted_server: str) -> None:
    """Covers: KAL-ENC-006"""
    page = fresh_page
    _unlock(page, _state["passphrase"])
    _left_unlock(page)
    page.goto(f"{encrypted_server}/settings?tab=security")
    page.get_by_role("button", name="Change passphrase").click()
    page.get_by_label("Current data passphrase").fill(_state["passphrase"])
    page.get_by_label("New data passphrase").fill(THIRD_PASSPHRASE)
    page.get_by_label("Repeat the passphrase").fill(THIRD_PASSPHRASE)
    page.get_by_role("button", name="Save").click()
    expect(page.get_by_text("Data passphrase changed.")).to_be_visible(timeout=20000)
    _state["passphrase"] = THIRD_PASSPHRASE

    page.get_by_role("button", name="Lock now").click()
    _unlock(page, THIRD_PASSPHRASE)
    _left_unlock(page)


def test_the_privacy_statement_says_what_is_encrypted(
    fresh_page: Page, encrypted_server: str
) -> None:
    """Covers: KAL-ENC-008"""
    _unlock(fresh_page, _state["passphrase"])
    _left_unlock(fresh_page)
    fresh_page.goto(f"{encrypted_server}/settings?tab=privacy")
    box = fresh_page.get_by_test_id("encryption-box")
    expect(box).to_contain_text("What is encrypted")
    expect(box).to_contain_text("what any transaction was for")
    expect(box).to_contain_text("their amounts, dates, types and currencies")
