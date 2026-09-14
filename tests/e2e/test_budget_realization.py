# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Annual Budget Planning — the Realization tab.

Covers: KAL-BUD-012, KAL-BUD-013, KAL-BUD-014

Artboard 2b: the status word becomes a pace bar, and the month's schedule
explains the rows the bar alone would misread.
Page URL: /budgets
"""

from __future__ import annotations

import calendar
import datetime
import re

from playwright.sync_api import Locator, Page, expect

from tests.e2e.seed_helpers import (
    seed_account,
    seed_budget,
    seed_category,
    seed_planned_transaction,
    seed_transaction,
)


def _style_pct(locator: Locator, prop: str) -> float:
    """Read a percentage out of an inline style, however the browser rounded it."""
    style = locator.get_attribute("style") or ""
    match = re.search(rf"{prop}:\s*([0-9.]+)%", style)
    assert match is not None, f"no {prop} in {style!r}"
    return float(match.group(1))


def _open_realization(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/budgets")
    page.get_by_role("tab", name="Realization").click()


def _row_for(page: Page, category_name: str) -> Locator:
    return page.locator("div.row").filter(has_text=category_name).last


def test_a_pace_bar_replaces_the_status_word(page: Page, base_url: str) -> None:
    """Covers: KAL-BUD-013

    Every row ends with a track filled to what was spent and a tick where the
    month stands, instead of a word the reader had to weigh against nothing.
    """
    # Read the date per test, not at import: a suite that crosses midnight
    # would otherwise assert the tick against yesterday.
    today = datetime.date.today()
    category = "Zywnosc Pace E2E"
    account = "PKO Pace E2E"
    cat_id = seed_category(category)
    acc_id = seed_account(account)
    # 5% of the budget is on track on every day of every month: WARNING needs
    # used_pct above elapsed_pct + 5, and elapsed is never negative. A test
    # that only passes after the 6th is a test that fails on the 1st.
    seed_budget(cat_id, 800.0, today.month, today.year)
    seed_transaction(acc_id, cat_id, 40.0, description="Lidl Pace E2E")

    _open_realization(page, base_url)

    row = _row_for(page, category)
    expect(row).to_be_visible(timeout=10000)

    # 40 of 800: the fill is a twentieth of the track, not a word.
    fill = row.locator(".k-pace__fill")
    expect(fill).to_be_visible()
    assert _style_pct(fill, "width") == 5.0

    # The tick sits where the month does, which is what the fill is measured
    # against — the one thing the status badge never showed.
    elapsed = today.day / calendar.monthrange(today.year, today.month)[1] * 100
    assert abs(_style_pct(row.locator(".k-pace__tick"), "left") - elapsed) < 0.01

    # The status word did not disappear; it explains the bar on hover.
    row.locator(".k-pace").hover()
    tooltip = page.locator(".q-tooltip").last
    expect(tooltip).to_be_visible(timeout=5000)
    expect(tooltip).to_contain_text("On track")
    expect(tooltip).to_contain_text("elapsed")

    # The header names the column after the bar, not after the badge.
    expect(page.get_by_text("Pace", exact=True).first).to_be_visible()
    expect(page.get_by_text("Status", exact=True)).to_have_count(0)


def test_a_row_paid_in_full_early_says_so(page: Page, base_url: str) -> None:
    """Covers: KAL-BUD-012

    Rent leaves on the 1st, so its bar is full while the month is barely
    elapsed. Without the line under it, the row reads as an overspend.
    """
    today = datetime.date.today()
    month_start = today.replace(day=1)
    category = "Czynsz Pace E2E"
    account = "PKO Rent Pace E2E"
    cat_id = seed_category(category)
    acc_id = seed_account(account)
    seed_budget(cat_id, 2000.0, today.month, today.year)
    # "once", not "monthly": an open-ended plan seeded into the shared e2e
    # database would show up in every later test that reads the schedule —
    # payment calendar, upcoming planned, the 30-day forecast.
    seed_planned_transaction(
        "Czynsz Pace E2E plan",
        2000.0,
        acc_id,
        frequency="once",
        category_id=cat_id,
        start_date=month_start,
    )
    seed_transaction(acc_id, cat_id, 2000.0, description="Czynsz Pace E2E tx")

    _open_realization(page, base_url)

    row = _row_for(page, category)
    expect(row).to_be_visible(timeout=10000)
    expect(row).to_contain_text(f"Paid in full on {month_start.day:02d}.{month_start.month:02d}")

    # Full bar, barely elapsed month — and still not painted as an overspend,
    # which is the whole point of the line above.
    fill = row.locator(".k-pace__fill")
    expect(fill).to_be_visible()
    assert _style_pct(fill, "width") == 100.0
    assert "--k-expense" not in (fill.get_attribute("style") or "")


def test_a_bill_still_to_come_is_named(page: Page, base_url: str) -> None:
    """Covers: KAL-BUD-014

    An empty bar on the 20th is not thrift if the bill simply has not been
    paid yet. The bill is seeded as due *today*, which is a date that exists
    in every month — "later this month" does not, on the 31st.
    """
    today = datetime.date.today()
    category = "Prad Pace E2E"
    account = "PKO Prad Pace E2E"
    cat_id = seed_category(category)
    acc_id = seed_account(account)
    seed_budget(cat_id, 400.0, today.month, today.year)
    seed_planned_transaction(
        "Prad Pace E2E plan",
        284.0,
        acc_id,
        frequency="once",
        category_id=cat_id,
        start_date=today,
    )

    _open_realization(page, base_url)

    row = _row_for(page, category)
    expect(row).to_be_visible(timeout=10000)
    expect(row).to_contain_text(f"284.00 planned for {today.day:02d}.{today.month:02d}")
