# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Report Builder.

Maps scenarios from docs/bdd.md — Feature: Report Builder.
Page URL: /reports/builder
"""

from __future__ import annotations

import re

from playwright.sync_api import Locator, Page, expect

from tests.e2e import seed_helpers as sh

BUILDER = "/reports/builder"
REPORT_NAME = "Spend by account E2E"


def _slots(page: Page) -> Locator:
    """The five clickable parts of the sentence, in reading order."""
    return page.locator(".k-slot")


def _slot_text(page: Page, index: int) -> str:
    # Each slot carries its label and an expand_more glyph; the label is the
    # first line of it.
    return _slots(page).nth(index).inner_text().split("\n")[0].strip()


def _pick(page: Page, slot_index: int, option: str) -> None:
    _slots(page).nth(slot_index).click()
    menu = page.locator(".q-menu:visible")
    expect(menu).to_be_visible(timeout=5000)
    menu.locator(".q-item").filter(has_text=option).first.click()


def test_sentence_reflects_state_and_a_saved_report_comes_back(page: Page, base_url: str) -> None:
    """Covers: KAL-RPT-001

    The sentence is the builder's only statement of what it is about to ask,
    so it has to follow the state both ways: when the user edits it, and when
    a saved report puts state back underneath it.
    """
    account_id = sh.seed_account("Reports Builder E2E Account")
    category_id = sh.seed_category("Reports Builder E2E Category")
    sh.seed_transaction(account_id, category_id, 120.0, description="reports builder e2e")

    page.goto(f"{base_url}{BUILDER}")
    # The header arrives before the sentence card below it, so wait for the
    # sentence itself rather than for the page around it.
    expect(_slots(page).first).to_be_visible(timeout=10000)

    # The defaults, read off the page rather than assumed.
    expect(_slots(page)).to_have_count(5)
    assert _slot_text(page, 0) == "Total Amount"
    assert _slot_text(page, 1) == "Category"
    assert _slot_text(page, 2) == "Expense"
    assert _slot_text(page, 3) == "This Year"
    assert _slot_text(page, 4) == "10"

    # Editing a slot changes the query it describes.
    _pick(page, 1, "Account")
    expect(_slots(page).nth(1)).to_contain_text("Account", timeout=5000)

    # And so does dragging a field from the rail onto its slot, which is the
    # affordance the old drop zones had.
    page.get_by_text("Count", exact=True).first.drag_to(_slots(page).nth(0))
    expect(_slots(page).nth(0)).to_contain_text("Count", timeout=5000)
    assert _slot_text(page, 1) == "Account", "the drop leaves the other slots alone"

    page.get_by_role("button", name="Run").click()
    expect(page.get_by_text("by Account", exact=False).first).to_be_visible(timeout=10000)

    # Save it, then come back to a builder that knows nothing.
    page.get_by_role("button", name="Save report").click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible(timeout=5000)
    dialog.get_by_label("Report Name").fill(REPORT_NAME)
    dialog.get_by_role("button", name="Save").click()
    expect(page.get_by_text("Report saved", exact=False).first).to_be_visible(timeout=10000)

    page.goto(f"{base_url}{BUILDER}")
    expect(_slots(page).first).to_be_visible(timeout=10000)
    assert _slot_text(page, 1) == "Category", "a fresh builder starts from the defaults"
    assert _slot_text(page, 0) == "Total Amount"

    page.get_by_text(REPORT_NAME, exact=True).click()

    # The saved state comes back through the same sentence that wrote it.
    expect(_slots(page).nth(1)).to_contain_text("Account", timeout=10000)
    expect(_slots(page).nth(0)).to_contain_text("Count")
    expect(page.get_by_text(REPORT_NAME, exact=True).first).to_be_visible()


def test_the_eyebrow_names_the_report_and_its_scope(page: Page, base_url: str) -> None:
    """Covers: KAL-RPT-003

    Artboard `3e` titles the screen "Reports" and moves the report's own
    name onto the line above it, the way every other screen names what is in
    hand — with the size of the ledger it is drawn from beside it, so a
    figure on the card is read against something.
    """
    account_id = sh.seed_account("Reports Eyebrow E2E Account")
    category_id = sh.seed_category("Reports Eyebrow E2E Category")
    sh.seed_transaction(account_id, category_id, 64.0, description="reports eyebrow e2e")
    saved = "Eyebrow Report E2E"

    page.goto(f"{base_url}{BUILDER}")
    eyebrow = page.locator("[data-page-eyebrow]")
    expect(eyebrow).to_be_visible(timeout=10000)

    # Unsaved, and drawn from however many rows the ledger holds — spaced,
    # never comma-grouped, and never nothing: this test seeded one itself.
    expect(eyebrow).to_contain_text("Unsaved report")
    expect(eyebrow).to_contain_text(re.compile(r"[1-9][0-9  ]* transactions? in the ledger"))

    page.get_by_role("button", name="Save report").click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible(timeout=5000)
    dialog.get_by_label("Report Name").fill(saved)
    dialog.get_by_role("button", name="Save").click()

    # Saved: the name takes the place of "Unsaved report" on the same line.
    expect(eyebrow).to_contain_text(saved, timeout=10000)
    expect(eyebrow).not_to_contain_text("Unsaved report")


def test_the_bar_result_reads_as_rows(page: Page, base_url: str) -> None:
    """Covers: KAL-RPT-002

    Ten labelled bars inside an ECharts canvas could not be selected,
    searched or read aloud, and the shares they were labelled with were
    buried in a tooltip. They are four columns of text and one div now.
    """
    account_id = sh.seed_account("Reports Bars E2E Account")
    big = sh.seed_category("Reports Bars E2E Big")
    small = sh.seed_category("Reports Bars E2E Small")
    sh.seed_transaction(account_id, big, 900.0, description="reports bars e2e big")
    sh.seed_transaction(account_id, small, 100.0, description="reports bars e2e small")

    page.goto(f"{base_url}{BUILDER}")
    expect(_slots(page).first).to_be_visible(timeout=10000)
    page.get_by_role("button", name="Run").click()

    rows = page.locator(".k-report-bar-row")
    expect(rows.first).to_be_visible(timeout=15000)

    # Every row carries four cells: name, track, value, share.
    first = rows.first
    expect(first.locator(".k-report-bar-track")).to_have_count(1)
    cells = [c.strip() for c in first.inner_text().split("\n") if c.strip()]
    assert len(cells) == 3, cells  # the track has no text of its own
    assert cells[2].endswith("%"), cells

    # Ranked largest first, which is what lets the ramp stand in for a legend.
    def _value(row_text: str) -> float:
        line = [c for c in row_text.split("\n") if c.strip()][1]
        return float(line.replace(" ", "").replace(",", ""))

    values = [_value(rows.nth(i).inner_text()) for i in range(min(rows.count(), 5))]
    assert values == sorted(values, reverse=True), values

    # And the total is on the card's title line, not on a row.
    expect(page.locator(".k-result-total")).to_be_visible()
