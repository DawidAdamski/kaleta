# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Reserve Funds.

Page URL: /wizard/safety-funds
"""

from __future__ import annotations

from playwright.sync_api import Page, expect

from tests.e2e.seed_helpers import seed_account, seed_reserve_fund, update_account


def _fill_number(scope: Page, label: str, value: str) -> None:
    field = scope.get_by_role("spinbutton", name=label, exact=True)
    field.click(click_count=3)
    field.fill(value)


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
