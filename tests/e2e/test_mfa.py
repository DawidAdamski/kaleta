# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Two-factor authentication.

Covers: KAL-AUTH-013, KAL-AUTH-014, KAL-AUTH-015
Covers: KAL-AUTH-016, KAL-AUTH-019, KAL-AUTH-020
Covers: KAL-AUTH-022

One test, not four: enrolling changes how every later login on this shared
instance behaves, so the whole life of a second factor — set up, sign in with
a code, sign in with a recovery code, turn off — runs in one place with one
teardown that guarantees the enrolment is gone whatever happened in between.
"""

from __future__ import annotations

import time
from collections.abc import Generator

import pyotp
import pytest
from playwright.sync_api import Locator, Page, expect

from tests.e2e import seed_helpers
from tests.e2e.conftest import E2E_PASSWORD, E2E_USERNAME

TOTP_INTERVAL = 30

#: The last TOTP step this test has spent. A code is single-use, so asking for
#: two codes inside one 30-second window has to yield two different steps.
_last_step = -1


@pytest.fixture
def no_enrolment_left_behind() -> Generator[None]:
    """Clear every enrolment either side of the test.

    What this cannot clear is the code limiter, which lives in the app
    process: the test ends by deliberately burning five wrong answers, so the
    e2e user is locked out of the code prompt for fifteen minutes afterwards.
    The default ephemeral server is thrown away with it, so this only bites a
    run pointed at a reused instance with ``KALETA_E2E_BASE_URL`` — there,
    this file cannot be run twice inside a quarter of an hour.
    """
    seed_helpers.disable_mfa_for_all()
    yield
    seed_helpers.disable_mfa_for_all()


def next_totp(secret: str) -> str:
    """A code the server has not seen yet, without sleeping out a whole step.

    The drift window accepts the next step as well as the current one, so the
    usual answer is instant; only a test that burns two codes in one window
    ever waits.
    """
    global _last_step  # noqa: PLW0603 — one clock, one cursor into it
    while True:
        current = int(time.time()) // TOTP_INTERVAL
        wanted = max(current, _last_step + 1)
        if wanted <= current + 1:
            _last_step = wanted
            return str(pyotp.TOTP(secret, interval=TOTP_INTERVAL).at(wanted * TOTP_INTERVAL))
        time.sleep(1)


def open_dialog(page: Page, heading: str) -> Locator:
    dialog = page.locator(".q-dialog:visible").filter(has_text=heading)
    expect(dialog).to_be_visible(timeout=10000)
    return dialog


def read_recovery_codes(dialog: Locator) -> list[str]:
    codes = [line.strip() for line in dialog.locator(".font-mono > div").all_inner_texts()]
    return [code for code in codes if code]


def open_security_tab(page: Page) -> None:
    page.goto("/settings")
    page.get_by_role("tab", name="Security").click()
    expect(page.get_by_text("Two-factor authentication").first).to_be_visible(timeout=10000)


def enrol(page: Page) -> tuple[str, list[str]]:
    """Walk the Settings dialog; return the secret and the recovery codes."""
    open_security_tab(page)
    expect(page.get_by_text("Off", exact=True).first).to_be_visible(timeout=10000)
    page.get_by_role("button", name="Set up").click()

    setup = open_dialog(page, "Set up two-factor authentication")
    # The QR is the whole point of the dialog: without it the secret has to be
    # typed into the phone by hand.
    expect(setup.locator("svg").first).to_be_visible()
    secret = setup.locator(".break-all").inner_text().strip()
    assert secret, "the dialog must also show the key for apps that cannot scan"

    setup.get_by_label("Code", exact=True).fill(next_totp(secret))
    setup.get_by_role("button", name="Confirm").click()

    recovery = open_dialog(page, "Recovery codes")
    codes = read_recovery_codes(recovery)
    recovery.get_by_role("button", name="Close").click()
    return secret, codes


def sign_in_with_password(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/login")
    page.get_by_label("Username", exact=True).fill(E2E_USERNAME)
    page.get_by_label("Password", exact=True).fill(E2E_PASSWORD)
    page.get_by_role("button", name="Log in").click()


def test_two_factor_authentication(
    page: Page,
    page_no_auth: Page,
    base_url: str,
    no_enrolment_left_behind: None,
) -> None:
    """Covers: KAL-AUTH-013, KAL-AUTH-014, KAL-AUTH-015
    Covers: KAL-AUTH-016, KAL-AUTH-019, KAL-AUTH-020
    Covers: KAL-AUTH-022
    """
    secret, codes = enrol(page)

    # KAL-AUTH-013 — the card now says it is on, and hands over ten codes.
    assert len(codes) == 10
    expect(page.get_by_text("On since").first).to_be_visible(timeout=10000)
    expect(page.get_by_text("10 recovery codes left").first).to_be_visible()

    # KAL-AUTH-014 — the password alone now lands on the code prompt.
    sign_in_with_password(page_no_auth, base_url)
    expect(page_no_auth).to_have_url(f"{base_url}/login/mfa?redirect_to=/", timeout=10000)

    # KAL-AUTH-016 — and that half-finished session opens nothing. Asked over
    # the same cookie jar the browser is holding, without following the
    # redirect, so what the guard answers is what is asserted.
    guard = page_no_auth.context.request
    blocked = guard.get(f"{base_url}/transactions", max_redirects=0)
    assert blocked.status in (302, 303, 307), blocked.status
    assert "/login" in blocked.headers["location"]
    assert guard.get(f"{base_url}/api/v1/accounts/").status == 401

    page_no_auth.goto(f"{base_url}/login/mfa")
    code_field = page_no_auth.get_by_label("6-digit code", exact=True)
    expect(code_field).to_be_visible(timeout=10000)
    code_field.fill("000000")
    page_no_auth.get_by_role("button", name="Verify").click()
    expect(page_no_auth.get_by_text("That code is not right.")).to_be_visible(timeout=10000)

    code_field.fill(next_totp(secret))
    page_no_auth.get_by_role("button", name="Verify").click()
    # Wait for where it lands, not merely for it to leave: "no longer the code
    # prompt" is true the instant the navigation starts, and the session
    # cookie this next line asks about is not in the jar yet at that instant.
    expect(page_no_auth).to_have_url(f"{base_url}/", timeout=15000)
    assert guard.get(f"{base_url}/transactions", max_redirects=0).status == 200

    # KAL-AUTH-015 — a recovery code gets in once, and only once.
    page_no_auth.context.clear_cookies()
    sign_in_with_password(page_no_auth, base_url)
    expect(page_no_auth).to_have_url(f"{base_url}/login/mfa?redirect_to=/", timeout=10000)
    page_no_auth.get_by_role("button", name="Use a recovery code").click()
    recovery_field = page_no_auth.get_by_label("Recovery code", exact=True)
    recovery_field.fill(codes[0])
    page_no_auth.get_by_role("button", name="Verify").click()
    expect(page_no_auth).to_have_url(f"{base_url}/", timeout=15000)

    page_no_auth.context.clear_cookies()
    sign_in_with_password(page_no_auth, base_url)
    expect(page_no_auth).to_have_url(f"{base_url}/login/mfa?redirect_to=/", timeout=10000)
    page_no_auth.get_by_role("button", name="Use a recovery code").click()
    page_no_auth.get_by_label("Recovery code", exact=True).fill(codes[0])
    page_no_auth.get_by_role("button", name="Verify").click()
    expect(page_no_auth.get_by_text("That code is not right.")).to_be_visible(timeout=10000)

    # KAL-AUTH-019 — reissuing replaces the whole set.
    open_security_tab(page)
    expect(page.get_by_text("9 recovery codes left").first).to_be_visible(timeout=10000)
    page.get_by_role("button", name="Recovery codes").click()
    reissued = open_dialog(page, "Recovery codes")
    fresh_codes = read_recovery_codes(reissued)
    reissued.get_by_role("button", name="Close").click()
    assert len(fresh_codes) == 10
    assert set(fresh_codes).isdisjoint(codes)
    expect(page.get_by_text("10 recovery codes left").first).to_be_visible(timeout=10000)

    # KAL-AUTH-022 — park a second browser at the code prompt first, so that
    # turning the factor off below happens underneath it.
    page_no_auth.context.clear_cookies()
    sign_in_with_password(page_no_auth, base_url)
    expect(page_no_auth).to_have_url(f"{base_url}/login/mfa?redirect_to=/", timeout=10000)

    # KAL-AUTH-020 — the password and a code turn it off, and the login goes
    # back to what it was.
    page.get_by_role("button", name="Turn off").click()
    disable = open_dialog(page, "Turn off two-factor authentication")
    disable.get_by_label("Password", exact=True).fill(E2E_PASSWORD)
    disable.get_by_label("Code", exact=True).fill(next_totp(secret))
    disable.get_by_role("button", name="Turn off").click()
    expect(page.get_by_text("Off", exact=True).first).to_be_visible(timeout=10000)

    # KAL-AUTH-022 — the parked prompt is now asking for something that no
    # longer exists. It says so and sends the visitor back, rather than
    # answering "that code is not right" and charging them a try for it.
    stranded = page_no_auth.get_by_label("6-digit code", exact=True)
    expect(stranded).to_be_visible(timeout=10000)
    stranded.fill("000000")
    page_no_auth.get_by_role("button", name="Verify").click()
    expect(page_no_auth).to_have_url(f"{base_url}/login?reason=mfa_gone", timeout=15000)
    expect(page_no_auth.get_by_text("Two-factor authentication was turned off.")).to_be_visible()

    page_no_auth.context.clear_cookies()
    sign_in_with_password(page_no_auth, base_url)
    expect(page_no_auth).to_have_url(f"{base_url}/", timeout=15000)

    # KAL-AUTH-020 — and a wrong answer says the same thing whichever half was
    # wrong, five times, and then says to wait. Telling the two apart would
    # make this dialog a password oracle for anyone at a signed-in browser.
    second_secret, _second_codes = enrol(page)
    page.get_by_role("button", name="Turn off").click()
    disable = open_dialog(page, "Turn off two-factor authentication")

    password_field = disable.get_by_label("Password", exact=True)
    code_field = disable.get_by_label("Code", exact=True)
    message = disable.locator(".text-negative")

    def attempt(password: str, code: str) -> str:
        password_field.fill(password)
        code_field.fill(code)
        disable.get_by_role("button", name="Turn off").click()
        # The handler empties the code field once it has judged the attempt,
        # which is the signal that the message on screen belongs to this try
        # and is not the one left over from the last.
        expect(code_field).to_have_value("", timeout=10000)
        return message.inner_text().strip()

    wrong_password = attempt("definitely-wrong", next_totp(second_secret))
    wrong_code = attempt(E2E_PASSWORD, "000000")
    assert wrong_password == wrong_code, (wrong_password, wrong_code)
    assert "password" in wrong_password.casefold()

    for _ in range(2):
        assert attempt(E2E_PASSWORD, "000000") == wrong_code
    locked = attempt(E2E_PASSWORD, "000000")
    assert "try again in" in locked.casefold(), locked
    expect(page.get_by_text("On since").first).to_be_visible(timeout=10000)
