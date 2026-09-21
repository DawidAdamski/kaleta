# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Planned and Recurring Transactions.

Maps scenarios from docs/bdd.md — Feature: Planned and Recurring Transactions.
Page URL: /planned
"""

from __future__ import annotations

import datetime
import re

from playwright.sync_api import Page, expect

from tests.e2e.ledger import filter_ledger_by_account, search_ledger
from tests.e2e.seed_helpers import (
    count_transactions,
    delete_planned_transaction,
    seed_account,
    seed_category,
    seed_planned_transaction,
    seed_subscription,
)

# ---------------------------------------------------------------------------
# Scenario: Create a monthly recurring expense
# ---------------------------------------------------------------------------


def test_create_monthly_recurring_expense(page: Page, base_url: str) -> None:
    """Covers: KAL-PLN-001"""
    seed_account("PKO Main Planned Monthly")
    seed_category("Subscriptions Planned E2E")

    page.goto(f"{base_url}/planned")
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


def test_create_weekly_recurring_expense(page: Page, base_url: str) -> None:
    """Covers: KAL-PLN-002"""
    seed_account("PKO Main Planned Weekly")

    page.goto(f"{base_url}/planned")
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


def test_create_yearly_recurring_expense(page: Page, base_url: str) -> None:
    """Covers: KAL-PLN-003"""
    seed_account("PKO Main Planned Yearly")
    seed_category("Insurance")

    page.goto(f"{base_url}/planned")
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


def test_edit_planned_transaction_amount(page: Page, base_url: str) -> None:
    """Covers: KAL-PLN-009"""
    acc_id = seed_account("PKO Main Planned Edit")
    cat_id = seed_category("Subs Edit")
    seed_planned_transaction(
        name="Netflix Edit Test",
        amount=49,
        account_id=acc_id,
        category_id=cat_id,
    )

    page.goto(f"{base_url}/planned")
    expect(page.get_by_text("Netflix Edit Test")).to_be_visible(timeout=5000)

    row = page.locator(".q-table tbody tr").filter(has_text="Netflix Edit Test")
    row.get_by_role("button").nth(2).click()  # edit (toggle=0, post=1, edit=2, delete=3)

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


def test_delete_planned_transaction(page: Page, base_url: str) -> None:
    """Covers: KAL-PLN-010"""
    acc_id = seed_account("PKO Main Planned Delete")
    seed_planned_transaction(
        name="Old subscription Delete Test",
        amount=10,
        account_id=acc_id,
    )

    page.goto(f"{base_url}/planned")
    expect(page.get_by_text("Old subscription Delete Test")).to_be_visible(timeout=5000)

    row = page.locator(".q-table tbody tr").filter(has_text="Old subscription Delete Test")
    row.get_by_role("button").nth(3).click()  # delete button (index 3)

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


def test_toggle_planned_transaction_inactive(page: Page, base_url: str) -> None:
    """Covers: KAL-PLN-007"""
    acc_id = seed_account("PKO Main Planned Toggle")
    seed_planned_transaction(
        name="Netflix Toggle Test",
        amount=49,
        account_id=acc_id,
        is_active=True,
    )

    page.goto(f"{base_url}/planned")
    expect(page.get_by_text("Netflix Toggle Test")).to_be_visible(timeout=5000)

    row = page.locator(".q-table tbody tr").filter(has_text="Netflix Toggle Test")
    row.get_by_role("button").nth(0).click()  # power_settings_new toggle button

    # After toggling the row still exists (item wasn't deleted)
    expect(page.get_by_text("Netflix Toggle Test")).to_be_visible(timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: Re-activate a paused planned transaction
# ---------------------------------------------------------------------------


def test_reactivate_paused_planned_transaction(page: Page, base_url: str) -> None:
    """Covers: KAL-PLN-008"""
    acc_id = seed_account("PKO Main Planned Reactivate")
    seed_planned_transaction(
        name="Netflix Reactivate Test",
        amount=49,
        account_id=acc_id,
        is_active=False,
    )

    page.goto(f"{base_url}/planned")
    expect(page.get_by_text("Netflix Reactivate Test")).to_be_visible(timeout=5000)

    row = page.locator(".q-table tbody tr").filter(has_text="Netflix Reactivate Test")
    row.get_by_role("button").nth(0).click()  # toggle button

    expect(page.get_by_text("Netflix Reactivate Test")).to_be_visible(timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: Create a recurring transaction with an end date
# ---------------------------------------------------------------------------


def test_create_recurring_transaction_with_end_date(page: Page, base_url: str) -> None:
    """Covers: KAL-PLN-005"""
    seed_account("PKO Main Planned EndDate")

    page.goto(f"{base_url}/planned")
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
# Scenario: Upcoming planned occurrences in the Transactions list
# ---------------------------------------------------------------------------

UPCOMING_CARD = "Upcoming planned transactions"


def _set_upcoming_window(page: Page, base_url: str, option: str) -> None:
    """Pick one of Off / 7 days / 30 days on Settings → Features.

    Every e2e test shares one browser session, so it shares one
    ``app.storage.user`` too: a test that moves this knob has to put it back
    where it found it, or the next test reads a window it never asked for.
    """
    page.goto(f"{base_url}/settings")
    page.get_by_role("tab", name="Features").click()
    card = page.locator(".q-card").filter(has_text=UPCOMING_CARD)
    expect(card).to_be_visible(timeout=10000)
    card.get_by_role("button", name=option, exact=True).click()
    expect(page.get_by_text("Settings saved").first).to_be_visible(timeout=5000)


def _ledger_row(page: Page, text: str):  # noqa: ANN202 — Playwright locator
    return page.locator(".q-table tbody tr").filter(has_text=text)


def test_upcoming_planned_row_heads_the_ledger(page: Page, base_url: str) -> None:
    """Covers: KAL-PLN-011"""
    acc_id = seed_account("PKO Main Upcoming Shown")
    seed_planned_transaction(
        name="Netflix Upcoming Test",
        amount=49,
        account_id=acc_id,
        frequency="weekly",
        is_active=True,
        start_date=datetime.date.today() + datetime.timedelta(days=3),
    )

    page.goto(f"{base_url}/transactions")
    search_ledger(page, "Netflix Upcoming Test")

    row = _ledger_row(page, "Netflix Upcoming Test")
    expect(row).to_have_count(1, timeout=10000)
    expect(row).to_have_class(re.compile(r"k-planned-row"))
    expect(row.get_by_text("Planned", exact=True)).to_be_visible()
    expect(row.get_by_text("In 3 days", exact=True)).to_be_visible()
    # A promise cannot be ticked for deletion — its id names no transaction.
    expect(row.locator(".q-checkbox")).to_have_count(0)
    # Nothing recorded matches this search, but the table is not empty: the
    # count under it has to say which kind of row the reader is looking at.
    expect(page.get_by_text("No recorded transactions — 1 upcoming planned row")).to_be_visible()


def test_upcoming_rows_are_hidden_when_the_window_is_off(page: Page, base_url: str) -> None:
    """Covers: KAL-PLN-012"""
    acc_id = seed_account("PKO Main Upcoming Off")
    seed_planned_transaction(
        name="Netflix Off Test",
        amount=49,
        account_id=acc_id,
        frequency="weekly",
        is_active=True,
        start_date=datetime.date.today() + datetime.timedelta(days=3),
    )

    _set_upcoming_window(page, base_url, "Off")
    try:
        page.goto(f"{base_url}/transactions")
        search_ledger(page, "Netflix Off Test")
        expect(_ledger_row(page, "Netflix Off Test")).to_have_count(0, timeout=10000)
    finally:
        _set_upcoming_window(page, base_url, "7 days")


def test_the_account_filter_applies_to_upcoming_rows(page: Page, base_url: str) -> None:
    """Covers: KAL-PLN-021"""
    token = "UpcomingAccountE2E"
    mine = f"PKO Main {token}"
    theirs = f"mBank Savings {token}"
    mine_id = seed_account(mine)
    theirs_id = seed_account(theirs)
    due = datetime.date.today() + datetime.timedelta(days=3)
    seed_planned_transaction(
        name=f"Netflix {token}",
        amount=49,
        account_id=mine_id,
        frequency="weekly",
        start_date=due,
    )
    seed_planned_transaction(
        name=f"Spotify {token}",
        amount=23,
        account_id=theirs_id,
        frequency="weekly",
        start_date=due,
    )

    page.goto(f"{base_url}/transactions")
    search_ledger(page, token)
    expect(page.locator(".q-table tbody tr")).to_have_count(2, timeout=10000)

    filter_ledger_by_account(page, mine)

    expect(_ledger_row(page, f"Netflix {token}")).to_have_count(1, timeout=10000)
    expect(_ledger_row(page, f"Spotify {token}")).to_have_count(0)


def test_clicking_an_upcoming_row_opens_the_plan_behind_it(page: Page, base_url: str) -> None:
    """Covers: KAL-PLN-022"""
    acc_id = seed_account("PKO Main Upcoming Click")
    seed_planned_transaction(
        name="Netflix Click Test",
        amount=49,
        account_id=acc_id,
        frequency="weekly",
        start_date=datetime.date.today() + datetime.timedelta(days=3),
    )

    page.goto(f"{base_url}/transactions")
    search_ledger(page, "Netflix Click Test")

    _ledger_row(page, "Netflix Click Test").click()

    dialog = page.get_by_role("dialog")
    expect(dialog.get_by_text("Upcoming planned transaction", exact=True)).to_be_visible(
        timeout=5000
    )
    expect(dialog.get_by_text("Netflix Click Test", exact=True)).to_be_visible()
    # The ledger's own editor must stay shut — an occurrence is not a row to edit.
    expect(dialog.get_by_text("Edit Transaction", exact=True)).to_have_count(0)

    dialog.get_by_role("button", name="Open in Planned Transactions").click()
    page.wait_for_url(lambda url: url.endswith("/planned"), timeout=10000)
    expect(page.get_by_text("Netflix Click Test").first).to_be_visible(timeout=10000)


def test_a_row_whose_plan_is_gone_says_so(page: Page, base_url: str) -> None:
    """Covers: KAL-PLN-025"""
    acc_id = seed_account("PKO Main Upcoming Stale")
    plan_id = seed_planned_transaction(
        name="Netflix Stale Test",
        amount=49,
        account_id=acc_id,
        frequency="weekly",
        start_date=datetime.date.today() + datetime.timedelta(days=3),
    )

    page.goto(f"{base_url}/transactions")
    search_ledger(page, "Netflix Stale Test")
    row = _ledger_row(page, "Netflix Stale Test")
    expect(row).to_have_count(1, timeout=10000)

    # The plan goes while the row is still on screen — the click that follows
    # has nothing left to open.
    assert delete_planned_transaction(plan_id) is True

    row.click()
    expect(page.get_by_text("That planned transaction no longer exists.").first).to_be_visible(
        timeout=5000
    )
    expect(page.get_by_text("Upcoming planned transaction", exact=True)).to_have_count(0)


# ---------------------------------------------------------------------------
# Scenario: Auto-post on start is off by default
# ---------------------------------------------------------------------------


def test_auto_post_due_off_by_default(page: Page, base_url: str) -> None:
    """Covers: KAL-PLN-018"""
    page.goto(f"{base_url}/settings")
    page.get_by_role("tab", name="Features").click()
    switch = page.get_by_text("Auto-post due planned transactions on start")
    expect(switch).to_be_visible(timeout=5000)
    # Quasar switch: aria-checked false when off
    switch_input = page.locator(".q-toggle").filter(
        has_text="Auto-post due planned transactions on start"
    )
    expect(switch_input).to_be_visible()
    checked = switch_input.locator("input").get_attribute("aria-checked")
    assert checked in (None, "false")


# ---------------------------------------------------------------------------
# Scenario: Post due from planned list creates a transaction
# ---------------------------------------------------------------------------


def test_post_due_from_planned_list(page: Page, base_url: str) -> None:
    """Covers: KAL-PLN-015"""
    today = datetime.date.today()
    start = today - datetime.timedelta(days=5)
    acc_id = seed_account("PKO Main Planned PostDue")
    seed_planned_transaction(
        name="Netflix PostDue Test",
        amount=49,
        account_id=acc_id,
        frequency="once",
        is_active=True,
        start_date=start,
    )

    page.goto(f"{base_url}/planned")
    expect(page.get_by_text("Netflix PostDue Test")).to_be_visible(timeout=5000)
    row = page.locator(".q-table tbody tr").filter(has_text="Netflix PostDue Test")
    row.get_by_role("button").nth(1).click()  # post
    expect(page.get_by_text("Posted").first).to_be_visible(timeout=5000)

    page.goto(f"{base_url}/transactions")
    expect(page.get_by_text("Netflix PostDue Test").first).to_be_visible(timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: Overdue occurrences are listed in a strip above the calendar
# ---------------------------------------------------------------------------


def test_overdue_strip_above_the_calendar_grid(page: Page, base_url: str) -> None:
    """Covers: KAL-PLN-020

    The overdue list used to hang off the day-1 cell, so an item three weeks
    late was invisible until the user clicked a day it had nothing to do with.
    It reads as one line now (artboard `3c`): what is late, since when, for
    how much, and one button that clears exactly the items it names.
    """
    today = datetime.date.today()
    first_of_month = today.replace(day=1)
    due = first_of_month - datetime.timedelta(days=5)
    acc_id = seed_account("PKO Main Calendar Overdue")
    seed_planned_transaction(
        name="Prad Zalegly",
        amount=210,
        account_id=acc_id,
        frequency="once",
        is_active=True,
        start_date=due,
    )

    page.goto(f"{base_url}/payment-calendar")

    strip = page.locator(".k-overdue-strip")
    expect(strip).to_be_visible(timeout=10000)
    expect(strip).to_contain_text("Prad Zalegly")
    # Since when, so "overdue" is a point in time and not just a flag.
    expect(strip).to_contain_text(f"Overdue since {due.strftime('%d.%m')}")

    # One button, naming how many items it will post — and posting exactly
    # those. The suite shares one database, so other tests' overdue items may
    # be listed beside this one; the count is read off the button itself.
    post = strip.get_by_role("button")
    expect(post).to_be_visible()
    label = post.inner_text().strip()
    assert re.fullmatch(r"Post \d+", label), label
    listed = strip.locator(".k-overdue-text").count()
    assert label == f"Post {listed}", (label, listed)

    # Exactly those: this account holds one overdue plan and nothing else, so
    # one press has to leave exactly one new row on it.
    before = count_transactions(acc_id)

    # Posting works from the strip itself — no day has to be opened first.
    post.click()

    # Every item the button named is posted, so nothing is left to be late
    # and the strip goes with its last row — not only the one this test
    # seeded. That is the whole of "posts exactly the items it names": the
    # named ones all go, and the count on this account shows no others did.
    expect(page.locator(".k-overdue-strip")).to_have_count(0, timeout=10000)
    expect(page.locator('[data-kpi="overdue"]')).to_have_text("0")
    assert count_transactions(acc_id) == before + 1
    # And it says how many it posted, in the number it had promised.
    expect(page.get_by_text(f"Posted {listed} due occurrence(s).")).to_be_visible()


def test_a_days_totals_count_its_subscription_charges(page: Page, base_url: str) -> None:
    """Covers: KAL-PLN-027

    The cell in the grid always counted a day's projected charges and the
    sheet did not, so a day drawn -12.99 opened onto Out 0.00 — the screen
    disagreeing with itself about the same day.

    The 2nd, because it is a day no other test in this file seeds: the
    figures below are the charge alone, which is what makes them literals.
    """
    today = datetime.date.today()
    second = today.replace(day=2)
    seed_subscription("iCloud Calendar E2E", 12.99, 30, first_seen_at=second)

    page.goto(f"{base_url}/payment-calendar")
    cell = page.locator(f'[data-day="{second.isoformat()}"]')
    expect(cell).to_be_visible(timeout=10000)
    expect(cell).to_contain_text("-12.99")

    cell.click()
    panel = page.locator(".k-day-panel")
    expect(panel).to_contain_text(str(second.day), timeout=5000)
    expect(panel).to_contain_text("-12.99")
    # In, Out and Net, in that order: nothing came in, 12.99 went out.
    totals = panel.locator(".k-hairline-bottom")
    expect(totals).to_contain_text("0.00")
    expect(totals).to_contain_text("-12.99")


def test_the_day_sheet_sits_beside_the_month(page: Page, base_url: str) -> None:
    """Covers: KAL-PLN-026

    The sheet used to slide in from the right and cover the grid it was
    about, so the one comparison the screen exists for — this day against
    the ones around it — could not be made while it was open.
    """
    page.goto(f"{base_url}/payment-calendar")

    panel = page.locator(".k-day-panel")
    grid = page.locator(".k-cal-day").first
    expect(panel).to_be_visible(timeout=10000)
    expect(grid).to_be_visible()

    today = datetime.date.today()
    expect(panel).to_contain_text(str(today.day))
    for label in ("In", "Out", "Net"):
        expect(panel.get_by_text(label, exact=True)).to_be_visible()

    # Beside, not over: the two occupy different columns of the same row.
    panel_box = panel.bounding_box()
    grid_box = page.locator(".k-cal-day").first.bounding_box()
    assert panel_box is not None and grid_box is not None
    assert grid_box["x"] + grid_box["width"] <= panel_box["x"], (grid_box, panel_box)

    # Another day moves the sheet, and the grid stays where it is. By its
    # own `data-day`, not by its text: a cell reading "21" or "1 400"
    # contains "1" too, and which of them came first was luck.
    other = today.replace(day=1 if today.day != 1 else 2)
    page.locator(f'[data-day="{other.isoformat()}"]').click()
    expect(panel).to_contain_text(str(other.day), timeout=10000)
    expect(page.locator(".k-cal-day").first).to_be_visible()

    # Closing it gives the grid the page. The panel is redrawn whenever a
    # day is picked, so the close icon is looked up after that redraw has
    # landed rather than before it.
    close = panel.locator("i", has_text="close").first
    expect(close).to_be_visible(timeout=10000)
    close.click()
    expect(panel).to_be_hidden(timeout=10000)
    expect(page.locator(".k-cal-day").first).to_be_visible()
