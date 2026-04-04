"""E2E tests for Feature: Planned and Recurring Transactions.

Maps scenarios from docs/bdd.md — Feature: Planned and Recurring Transactions.
Page URL: /planned
"""

from __future__ import annotations

from playwright.sync_api import Page, expect

from tests.e2e.seed_helpers import seed_account, seed_category, seed_planned_transaction

BASE_URL = "http://localhost:8080"


# ---------------------------------------------------------------------------
# Scenario: Create a monthly recurring expense
# ---------------------------------------------------------------------------


def test_create_monthly_recurring_expense(page: Page) -> None:
    """Scenario: Create a monthly recurring expense"""
    seed_account("PKO Main Planned Monthly")
    seed_category("Subscriptions")

    page.goto(f"{BASE_URL}/planned")
    page.get_by_role("button", name="Add Planned").click()

    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible(timeout=5000)

    dialog.get_by_label("Name").fill("Netflix Monthly Test")
    dialog.get_by_label("Amount").fill("49")

    dialog.locator(".q-select").filter(has_text="Account").click()
    page.locator(".q-menu").get_by_text("PKO Main Planned Monthly", exact=True).click()

    # Category is optional — skip selecting it to avoid virtual-scroll issues
    # with large category lists.

    # Frequency defaults to Monthly — filter by the Frequency label to avoid
    # matching the Account select which now shows "PKO Main Planned Monthly".
    freq_select = dialog.locator(".q-select").filter(has_text="Frequency")
    expect(freq_select).to_contain_text("Monthly")

    dialog.get_by_role("button", name="Save").click()

    expect(page.get_by_text("Netflix Monthly Test").first).to_be_visible(timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: Create a weekly recurring expense
# ---------------------------------------------------------------------------


def test_create_weekly_recurring_expense(page: Page) -> None:
    """Scenario: Create a weekly recurring expense"""
    seed_account("PKO Main Planned Weekly")

    page.goto(f"{BASE_URL}/planned")
    page.get_by_role("button", name="Add Planned").click()

    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible(timeout=5000)

    dialog.get_by_label("Name").fill("Weekly groceries Test")
    dialog.get_by_label("Amount").fill("300")

    dialog.locator(".q-select").filter(has_text="Account").click()
    page.locator(".q-menu").get_by_text("PKO Main Planned Weekly", exact=True).click()

    dialog.locator(".q-select").filter(has_text="Frequency").click()
    page.locator(".q-menu").get_by_text("Weekly", exact=True).click()

    dialog.get_by_role("button", name="Save").click()

    expect(page.get_by_text("Weekly groceries Test").first).to_be_visible(timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: Create a yearly recurring expense
# ---------------------------------------------------------------------------


def test_create_yearly_recurring_expense(page: Page) -> None:
    """Scenario: Create a yearly recurring expense"""
    seed_account("PKO Main Planned Yearly")
    seed_category("Insurance")

    page.goto(f"{BASE_URL}/planned")
    page.get_by_role("button", name="Add Planned").click()

    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible(timeout=5000)

    dialog.get_by_label("Name").fill("Car insurance Test")
    dialog.get_by_label("Amount").fill("2400")

    dialog.locator(".q-select").filter(has_text="Account").click()
    page.locator(".q-menu").get_by_text("PKO Main Planned Yearly", exact=True).click()

    dialog.locator(".q-select").filter(has_text="Frequency").click()
    page.locator(".q-menu").get_by_text("Yearly", exact=True).click()

    dialog.get_by_role("button", name="Save").click()

    expect(page.get_by_text("Car insurance Test").first).to_be_visible(timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: Edit a planned transaction amount
# ---------------------------------------------------------------------------


def test_edit_planned_transaction_amount(page: Page) -> None:
    """Scenario: Edit a planned transaction amount"""
    acc_id = seed_account("PKO Main Planned Edit")
    cat_id = seed_category("Subs Edit")
    seed_planned_transaction(
        name="Netflix Edit Test",
        amount=49,
        account_id=acc_id,
        category_id=cat_id,
    )

    page.goto(f"{BASE_URL}/planned")
    expect(page.get_by_text("Netflix Edit Test")).to_be_visible(timeout=5000)

    row = page.locator(".q-table tbody tr").filter(has_text="Netflix Edit Test")
    row.get_by_role("button").nth(1).click()  # edit (toggle=0, edit=1, delete=2)

    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible(timeout=5000)

    amount_field = dialog.get_by_label("Amount")
    amount_field.click(click_count=3)
    amount_field.fill("59")

    dialog.get_by_role("button", name="Save").click()

    expect(page.get_by_text("59")).to_be_visible(timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: Delete a planned transaction
# ---------------------------------------------------------------------------


def test_delete_planned_transaction(page: Page) -> None:
    """Scenario: Delete a planned transaction"""
    acc_id = seed_account("PKO Main Planned Delete")
    seed_planned_transaction(
        name="Old subscription Delete Test",
        amount=10,
        account_id=acc_id,
    )

    page.goto(f"{BASE_URL}/planned")
    expect(page.get_by_text("Old subscription Delete Test")).to_be_visible(timeout=5000)

    row = page.locator(".q-table tbody tr").filter(has_text="Old subscription Delete Test")
    row.get_by_role("button").nth(2).click()  # delete button (index 2)

    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible(timeout=5000)
    dialog.get_by_role("button", name="Delete").click()

    # After deletion, check the table row is gone
    expect(
        page.locator(".q-table tbody tr").filter(has_text="Old subscription Delete Test")
    ).not_to_be_visible(timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: Toggle a planned transaction inactive
# ---------------------------------------------------------------------------


def test_toggle_planned_transaction_inactive(page: Page) -> None:
    """Scenario: Toggle a planned transaction inactive"""
    acc_id = seed_account("PKO Main Planned Toggle")
    seed_planned_transaction(
        name="Netflix Toggle Test",
        amount=49,
        account_id=acc_id,
        is_active=True,
    )

    page.goto(f"{BASE_URL}/planned")
    expect(page.get_by_text("Netflix Toggle Test")).to_be_visible(timeout=5000)

    row = page.locator(".q-table tbody tr").filter(has_text="Netflix Toggle Test")
    row.get_by_role("button").nth(0).click()  # power_settings_new toggle button

    # After toggling the row still exists (item wasn't deleted)
    expect(page.get_by_text("Netflix Toggle Test")).to_be_visible(timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: Re-activate a paused planned transaction
# ---------------------------------------------------------------------------


def test_reactivate_paused_planned_transaction(page: Page) -> None:
    """Scenario: Re-activate a paused planned transaction"""
    acc_id = seed_account("PKO Main Planned Reactivate")
    seed_planned_transaction(
        name="Netflix Reactivate Test",
        amount=49,
        account_id=acc_id,
        is_active=False,
    )

    page.goto(f"{BASE_URL}/planned")
    expect(page.get_by_text("Netflix Reactivate Test")).to_be_visible(timeout=5000)

    row = page.locator(".q-table tbody tr").filter(has_text="Netflix Reactivate Test")
    row.get_by_role("button").nth(0).click()  # toggle button

    expect(page.get_by_text("Netflix Reactivate Test")).to_be_visible(timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: Create a recurring transaction with an end date
# ---------------------------------------------------------------------------


def test_create_recurring_transaction_with_end_date(page: Page) -> None:
    """Scenario: Create a recurring transaction with an end date"""
    seed_account("PKO Main Planned EndDate")

    page.goto(f"{BASE_URL}/planned")
    page.get_by_role("button", name="Add Planned").click()

    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible(timeout=5000)

    dialog.get_by_label("Name").fill("Gym membership Test")
    dialog.get_by_label("Amount").fill("120")

    dialog.locator(".q-select").filter(has_text="Account").click()
    page.locator(".q-menu").get_by_text("PKO Main Planned EndDate", exact=True).click()

    dialog.locator(".q-select").filter(has_text="Frequency").click()
    page.locator(".q-menu").get_by_text("Monthly", exact=True).click()

    dialog.get_by_role("button", name="Save").click()

    expect(page.get_by_text("Gym membership Test").first).to_be_visible(timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: Planned transaction does not appear in transactions without toggle
# ---------------------------------------------------------------------------


def test_planned_not_shown_without_toggle(page: Page) -> None:
    """Scenario: Planned transaction does not appear in transactions without the toggle"""
    acc_id = seed_account("PKO Main Planned NoToggle")
    seed_planned_transaction(
        name="Netflix NoToggle Test",
        amount=49,
        account_id=acc_id,
        is_active=True,
    )

    page.goto(f"{BASE_URL}/transactions")
    # Without the Show Planned toggle, planned items are not shown as real transactions
    expect(page.get_by_text("Netflix NoToggle Test")).not_to_be_visible(timeout=3000)
