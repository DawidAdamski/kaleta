# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Report Builder.

Maps scenarios from docs/bdd.md — Feature: Report Builder.
Page URL: /reports/builder
"""

from __future__ import annotations

import datetime
import re

from playwright.sync_api import Locator, Page, expect

from tests.e2e import seed_helpers as sh

BUILDER = "/reports/builder"
REPORT_NAME = "Spend by account E2E"


def _slots(page: Page) -> Locator:
    """The six clickable parts of the sentence, in reading order.

    Measure, grouping, second dimension, types, period, top N. The third is
    the optional one and is drawn whether or not it has been used, so the
    indices below are the same in both states.
    """
    return page.locator(".k-slot")


#: The glyph names a material icon renders as text, which `inner_text` reads
#: alongside the slot's own word.
_ICON_WORDS = {"expand_more", "add"}


def _slot_text(page: Page, index: int) -> str:
    # Each slot carries its label and a glyph; the label is whichever line is
    # not the glyph's own name.
    lines = [
        line.strip()
        for line in _slots(page).nth(index).inner_text().split("\n")
        if line.strip() and line.strip() not in _ICON_WORDS
    ]
    return lines[0] if lines else ""


def _pick(page: Page, slot_index: int, option: str) -> None:
    """Open a slot's menu and choose one option by its exact word.

    Waits for the previous menu to finish closing first: a menu still fading
    out is still visible, and picking through it would choose an option from
    the slot before. Exact text for the same reason — "Month" is a word
    inside "This Month".
    """
    expect(page.locator(".q-menu:visible")).to_have_count(0, timeout=5000)
    _slots(page).nth(slot_index).click()
    menu = page.locator(".q-menu:visible")
    expect(menu).to_be_visible(timeout=5000)
    menu.get_by_text(option, exact=True).first.click()


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
    expect(_slots(page)).to_have_count(6)
    assert _slot_text(page, 0) == "Total Amount"
    assert _slot_text(page, 1) == "Category"
    assert _slot_text(page, 2) == "by …", "the second dimension starts unused"
    assert _slot_text(page, 3) == "Expense"
    assert _slot_text(page, 4) == "This Year"
    assert _slot_text(page, 5) == "10"

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
    # 15s, longer than this file's other waits: Run groups the whole seeded
    # ledger in the service before a single row is drawn, and this is the
    # only assertion in the suite that waits on that query rather than on a
    # page already holding its answer.
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


def test_a_total_is_only_shown_where_the_rows_add_up(page: Page, base_url: str) -> None:
    """Covers: KAL-RPT-004

    The card's title line captions its figure "total". Summing a column of
    averages produces a number that is not the average of anything, so on
    that measure the caption is not drawn at all rather than drawn over a
    figure nobody can use.
    """
    account_id = sh.seed_account("Reports Total E2E Account")
    category_id = sh.seed_category("Reports Total E2E Category")
    sh.seed_transaction(account_id, category_id, 300.0, description="reports total e2e a")
    sh.seed_transaction(account_id, category_id, 500.0, description="reports total e2e b")

    page.goto(f"{base_url}{BUILDER}")
    expect(_slots(page).first).to_be_visible(timeout=10000)

    page.get_by_role("button", name="Run").click()
    total = page.locator(".k-result-total")
    expect(total).to_be_visible(timeout=15000)
    expect(total).to_contain_text("total")

    _pick(page, 0, "Average")
    page.get_by_role("button", name="Run").click()
    # The rows are still drawn; it is the caption over them that goes.
    expect(page.locator(".k-report-bar-row").first).to_be_visible(timeout=15000)
    expect(total).to_have_count(0)


# ---------------------------------------------------------------------------
# Feature: a second dimension (KAL-RPT-005 .. 007)
# ---------------------------------------------------------------------------

PIVOT_MONTHS = ("2025-01", "2025-02")


def _seed_two_months(prefix: str) -> None:
    """One category with spend in two named months, big enough to survive top N.

    The e2e ledger is shared, so the figures are chosen to rank inside the
    default top 10 whatever else the suite has seeded.
    """
    account_id = sh.seed_account(f"{prefix} Account")
    category_id = sh.seed_category(f"{prefix} Category")
    sh.seed_transaction(
        account_id, category_id, 9000.0, date=datetime.date(2025, 1, 15), description=prefix
    )
    sh.seed_transaction(
        account_id, category_id, 7000.0, date=datetime.date(2025, 2, 15), description=prefix
    )


def _chart_type(page: Page, index: int) -> None:
    """One of the five chart squares: bar, line, pie, donut, table."""
    page.locator(".k-chart-pick").nth(index).click()


def test_a_second_dimension_turns_the_table_into_a_pivot(page: Page, base_url: str) -> None:
    """Covers: KAL-RPT-005

    One dimension answers "how much per category"; the question people bring
    is "per category per month", which used to be twelve reports run by hand.
    """
    _seed_two_months("Reports Pivot E2E")

    page.goto(f"{base_url}{BUILDER}")
    expect(_slots(page).first).to_be_visible(timeout=10000)

    # All time, because the seeded months are not this year's.
    _pick(page, 4, "All Time")
    _pick(page, 2, "Month")
    expect(_slots(page).nth(2)).to_contain_text("Month", timeout=5000)
    _chart_type(page, 4)  # Table
    page.get_by_role("button", name="Run").click()

    grid = page.locator(".k-pivot")
    expect(grid).to_be_visible(timeout=15000)

    # A column per month, and the row axis still named by its own header.
    # Upper-cased because the column heads are, in CSS: what is asserted is
    # which words are there, not how the sheet sets them.
    headers = [cell.strip().upper() for cell in grid.locator(".k-pivot-head").all_inner_texts()]
    assert headers[0] == "CATEGORY", headers
    for month in PIVOT_MONTHS:
        assert month in headers, headers
    assert headers[-1] == "TOTAL", headers

    # The seeded row: its two months, and its own total beside them.
    row = grid.locator(".k-pivot-cell", has_text="Reports Pivot E2E Category").first
    expect(row).to_be_visible()
    figures = [
        cell.strip()
        for cell in grid.locator(".k-pivot-cell.k-pivot-figure").all_inner_texts()
        if cell.strip()
    ]
    assert "9 000.00" in figures, figures
    assert "7 000.00" in figures, figures
    assert "16 000.00" in figures, "the row carries its own total"

    # And the grid ends in a Total row of its own.
    expect(grid.locator(".k-pivot-foot").first).to_be_visible()


def test_with_a_second_dimension_the_bars_stack(page: Page, base_url: str) -> None:
    """Covers: KAL-RPT-006

    A ranking of rows cannot show what each row is made of, so with a series
    the rank rows give way to one stacked bar per row. The stacking and the
    legend entries themselves are asserted on the option dict in
    ``tests/unit/views/test_reports_chart_options.py``; what the browser can
    say is which of the two shapes was drawn.
    """
    _seed_two_months("Reports Stack E2E")

    page.goto(f"{base_url}{BUILDER}")
    expect(_slots(page).first).to_be_visible(timeout=10000)

    _pick(page, 4, "All Time")
    page.get_by_role("button", name="Run").click()
    # One dimension: the ranked rows, and no chart canvas at all.
    expect(page.locator(".k-report-bar-row").first).to_be_visible(timeout=15000)
    expect(page.locator(".nicegui-echart")).to_have_count(0)

    _pick(page, 2, "Month")
    page.get_by_role("button", name="Run").click()

    expect(page.locator(".nicegui-echart").first).to_be_visible(timeout=15000)
    expect(page.locator(".k-report-bar-row")).to_have_count(0)


def test_a_saved_report_without_a_second_dimension_loads_unchanged(
    page: Page, base_url: str
) -> None:
    """Covers: KAL-RPT-007

    Every `saved_reports.config` written before the second dimension existed
    has no "series" in it. They must come back as the one-dimensional reports
    they were saved as, not as an empty pivot.
    """
    _seed_two_months("Reports Legacy E2E")
    saved = "Legacy One Dimension E2E"

    page.goto(f"{base_url}{BUILDER}")
    expect(_slots(page).first).to_be_visible(timeout=10000)
    _pick(page, 4, "All Time")
    page.get_by_role("button", name="Run").click()
    expect(page.locator(".k-report-bar-row").first).to_be_visible(timeout=15000)

    page.get_by_role("button", name="Save report").click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible(timeout=5000)
    dialog.get_by_label("Report Name").fill(saved)
    dialog.get_by_role("button", name="Save").click()
    expect(page.get_by_text("Report saved", exact=False).first).to_be_visible(timeout=10000)

    page.goto(f"{base_url}{BUILDER}")
    expect(_slots(page).first).to_be_visible(timeout=10000)
    page.get_by_text(saved, exact=True).click()

    # Loading it runs it: the rank rows come back, the pivot grid does not,
    # and the second dimension still reads as unused.
    expect(page.locator(".k-report-bar-row").first).to_be_visible(timeout=15000)
    expect(page.locator(".k-pivot")).to_have_count(0)
    assert _slot_text(page, 2) == "by …"
