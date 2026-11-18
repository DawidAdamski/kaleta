# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Reserve Funds.

Page URL: /wizard/safety-funds
"""

from __future__ import annotations

from playwright.sync_api import Locator, Page, expect

from tests.e2e.seed_helpers import (
    delete_account,
    delete_reserve_fund,
    seed_account,
    seed_reserve_fund,
    update_account,
)


def _fill_number(scope: Page, label: str, value: str) -> None:
    field = scope.get_by_role("spinbutton", name=label, exact=True)
    field.click(click_count=3)
    field.fill(value)


def _select_fund_type(page: Page, dialog: Locator, option: str) -> None:
    dialog.locator(".q-select").filter(has_text="Fund type").click()
    page.locator(".q-menu").get_by_text(option, exact=True).click()


def test_switching_fund_type_back_to_emergency_restores_its_fields(
    page: Page, base_url: str
) -> None:
    """Covers: KAL-FND-004

    The Emergency fund type shows "Cover [N] months of expenses" and the
    "Derive target from my spending" switch. Switching the fund type away hides
    them; switching back to Emergency must bring them back (dogfooding #20 — it
    used to leave the dialog stuck in the reduced layout with no way back to the
    months-to-cover input). Opens the Add dialog and never saves, so the only
    cleanup needed is the seeded backing account (the dialog won't open without
    one).
    """
    account_id = seed_account("Emergency Toggle FND004 E2E")
    try:
        page.goto(f"{base_url}/wizard/safety-funds")
        expect(page.get_by_text("Safety & Reserve Funds", exact=True).first).to_be_visible(
            timeout=5000
        )

        page.get_by_role("button", name="Add fund").click()
        dialog = page.get_by_role("dialog")
        expect(dialog).to_be_visible(timeout=5000)

        cover = dialog.get_by_text("months of expenses", exact=True)
        derive = dialog.get_by_text("Derive target from my spending", exact=True)
        # Emergency is the default kind: both emergency-only controls are shown.
        expect(cover).to_be_visible()
        expect(derive).to_be_visible()

        _select_fund_type(page, dialog, "Irregular expenses")
        expect(cover).not_to_be_visible()
        expect(derive).not_to_be_visible()

        _select_fund_type(page, dialog, "Emergency fund")
        # Back on Emergency the two controls must reappear — the bug left them
        # hidden, stranding the months-to-cover input.
        expect(cover).to_be_visible()
        expect(derive).to_be_visible()
    finally:
        delete_account(account_id)


def test_emergency_cash_shows_balance_against_target(page: Page, base_url: str) -> None:
    """Covers: KAL-FND-001

    An emergency reserve fund shows the backing account balance against its target.
    """
    account_name = "Emergency cash FND E2E"
    account_id = seed_account(account_name)
    update_account(account_id, balance="1500.00", type="cash")

    page.goto(f"{base_url}/wizard/safety-funds")
    expect(page.get_by_text("Safety & Reserve Funds", exact=True).first).to_be_visible(timeout=5000)

    page.get_by_role("button", name="Add fund").click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible(timeout=5000)

    dialog.get_by_label("Name").fill("Emergency cash FND E2E")
    _fill_number(dialog, "Target amount", "3000")

    dialog.locator(".q-select").filter(has_text="Backing account").click()
    page.locator(".q-menu").get_by_text(account_name, exact=True).click()

    dialog.get_by_role("button", name="Save").click()

    expect(page.get_by_text("Emergency cash FND E2E", exact=True)).to_be_visible(timeout=5000)
    expect(page.get_by_text("1,500.00 / 3,000.00", exact=True)).to_be_visible(timeout=5000)


def test_dashboard_warns_when_reserve_is_below_target(page: Page, base_url: str) -> None:
    """Covers: KAL-FND-003

    "Emergency cash" holding 1800.00 against a 3000.00 target raises a
    below-target warning in the dashboard's wizard actions widget.
    """
    account_id = seed_account("Emergency cash account FND3 E2E")
    update_account(account_id, balance="1800.00", type="cash")
    seed_reserve_fund("Emergency cash", 3000.0, account_id)

    page.goto(f"{base_url}/")
    widget = page.locator('[data-widget-id="wizard_actions"]')
    expect(widget).to_be_visible(timeout=10000)

    row = widget.locator('[data-action-kind="fund_below_target"]').filter(
        has_text="Emergency cash is below target"
    )
    expect(row).to_have_count(1, timeout=10000)
    expect(row).to_have_attribute("data-severity", "warning")


def test_security_fund_target_derives_from_spending(page: Page, base_url: str) -> None:
    """Covers: KAL-FND-002

    UI path of the derived target: switching "Derive target from my spending"
    on locks the manual target, the hint shows the figure the service will
    use, and the saved card shows that figure as its target. The 15600.00
    literal itself is asserted in the service test — the e2e database is
    shared across tests, so its 12-month average is not under this test's
    control.
    """
    account_name = "Security fund FND2 E2E"
    account_id = seed_account(account_name)
    update_account(account_id, balance="0.00")

    page.goto(f"{base_url}/wizard/safety-funds")
    expect(page.get_by_text("Safety & Reserve Funds", exact=True).first).to_be_visible(timeout=5000)

    page.get_by_role("button", name="Add fund").click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible(timeout=5000)

    dialog.get_by_label("Name").fill("Security fund")
    _fill_number(dialog, "Target amount", "1")
    dialog.get_by_text("Derive target from my spending", exact=True).click()

    expect(dialog.get_by_role("spinbutton", name="Target amount", exact=True)).to_be_disabled()
    hint = dialog.get_by_text("× average monthly spending over the last 12 months")
    expect(hint).to_be_visible(timeout=5000)
    expect(hint).to_contain_text("last 90 days")
    derived = hint.inner_text().split("→ ")[1].split(")")[0]

    # Filter the searchable select: by this point in the suite there are more
    # accounts than the menu renders, so the target may not be in the list.
    account_select = dialog.locator(".q-select").filter(has_text="Backing account")
    account_select.click()
    account_select.locator("input").fill(account_name)
    page.locator(".q-menu").get_by_text(account_name, exact=True).click()

    dialog.get_by_role("button", name="Save").click()

    card = (
        page.locator(".q-card")
        .filter(has_text="Security fund")
        .filter(has_text="derived from spending")
    )
    expect(card).to_have_count(1, timeout=5000)
    expect(card.get_by_text(f"0.00 / {derived}", exact=True)).to_be_visible(timeout=5000)


# ── Reservoir layout (KAL-RSV) ────────────────────────────────────────────────
# The page is shared with every other test's funds, so each locator is scoped
# to the reservoir whose aria-label starts with this test's own fund name.


def _seed_backed_fund(name: str, balance: str, target: float) -> tuple[int, int]:
    account_id = seed_account(f"{name} account")
    update_account(account_id, balance=balance, type="cash")
    return seed_reserve_fund(name, target, account_id), account_id


def _reservoir(page: Page, fund_name: str) -> Locator:
    return page.locator(f'svg.k-reservoir[aria-label^="{fund_name}:"]')


def _fund_card(page: Page, fund_name: str) -> Locator:
    return page.locator(".q-card").filter(has=page.get_by_text(fund_name, exact=True))


def test_toggle_switches_to_the_reservoir_layout(page: Page, base_url: str) -> None:
    """Covers: KAL-RSV-001

    A fund holding 1500.00 against 3000.00 is a progress bar by default; the
    Reservoirs toggle swaps the card body for a reservoir filled to 50%, and
    Bars brings the progress bar back.
    """
    name = "Reservoir toggle RSV001"
    fund_id, account_id = _seed_backed_fund(name, "1500.00", 3000.0)
    try:
        page.goto(f"{base_url}/wizard/safety-funds")
        card = _fund_card(page, name)
        expect(card.locator(".q-linear-progress")).to_have_count(1, timeout=5000)
        expect(_reservoir(page, name)).to_have_count(0)

        page.get_by_text("Reservoirs", exact=True).click()
        page.wait_for_url("**/wizard/safety-funds?layout=reservoirs")
        reservoir = _reservoir(page, name)
        expect(reservoir).to_have_count(1, timeout=5000)
        expect(reservoir).to_have_attribute("data-state", "partial")
        expect(reservoir).to_have_attribute("data-percent", "50")
        expect(reservoir).to_have_attribute("aria-label", f"{name}: 1,500.00 of 3,000.00 PLN, 50%")
        expect(_fund_card(page, name).locator(".q-linear-progress")).to_have_count(0)

        page.get_by_text("Bars", exact=True).click()
        page.wait_for_url("**/wizard/safety-funds")
        expect(_fund_card(page, name).locator(".q-linear-progress")).to_have_count(1, timeout=5000)
        expect(_reservoir(page, name)).to_have_count(0)
    finally:
        delete_reserve_fund(fund_id)
        delete_account(account_id)


def test_fund_at_target_shows_a_full_reservoir(page: Page, base_url: str) -> None:
    """Covers: KAL-RSV-002"""
    name = "Reservoir full RSV002"
    fund_id, account_id = _seed_backed_fund(name, "3000.00", 3000.0)
    try:
        page.goto(f"{base_url}/wizard/safety-funds?layout=reservoirs")
        reservoir = _reservoir(page, name)
        expect(reservoir).to_have_attribute("data-state", "full", timeout=5000)
        expect(reservoir).to_have_attribute("data-percent", "100")
        expect(reservoir.locator("text.k-reservoir__label")).to_have_text("100%")
    finally:
        delete_reserve_fund(fund_id)
        delete_account(account_id)


def test_overfunded_fund_shows_the_overflow_state(page: Page, base_url: str) -> None:
    """Covers: KAL-RSV-003"""
    name = "Reservoir overflow RSV003"
    fund_id, account_id = _seed_backed_fund(name, "3900.00", 3000.0)
    try:
        page.goto(f"{base_url}/wizard/safety-funds?layout=reservoirs")
        reservoir = _reservoir(page, name)
        expect(reservoir).to_have_attribute("data-state", "overflow", timeout=5000)
        expect(reservoir.locator("path.k-reservoir__spill")).to_have_count(1)
        expect(reservoir.locator("text.k-reservoir__label")).to_have_text("130% — over target")
    finally:
        delete_reserve_fund(fund_id)
        delete_account(account_id)


def test_fund_without_target_degrades_to_the_empty_reservoir(page: Page, base_url: str) -> None:
    """Covers: KAL-RSV-004"""
    name = "Reservoir no target RSV004"
    fund_id, account_id = _seed_backed_fund(name, "500.00", 0.0)
    try:
        page.goto(f"{base_url}/wizard/safety-funds?layout=reservoirs")
        reservoir = _reservoir(page, name)
        expect(reservoir).to_have_attribute("data-state", "unavailable", timeout=5000)
        expect(reservoir.locator("rect.k-reservoir__water")).to_have_count(0)
        expect(reservoir.locator("text.k-reservoir__label")).to_have_text("—")
        note = _fund_card(page, name).locator(".k-reservoir__note")
        expect(note).to_have_text("No target or backing account")
    finally:
        delete_reserve_fund(fund_id)
        delete_account(account_id)
