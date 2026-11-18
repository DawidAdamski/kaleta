# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Annual Budget Planning — one Budgets page, three tabs.

Covers: KAL-BUD-019, KAL-BUD-020, KAL-BUD-021, KAL-BUD-022

Planning and realization are one destination: the page opens where the month
is checked, both tabs look at the same month, and a row that is off its plan
links straight to the amount that set it.
Page URL: /budgets
"""

from __future__ import annotations

import datetime
import re

from playwright.sync_api import Locator, Page, expect

from tests.e2e.seed_helpers import seed_budget, seed_category

MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def _tab(page: Page, name: str) -> Locator:
    return page.get_by_role("tab", name=name, exact=True)


def _pick(page: Page, select: Locator, option: str) -> None:
    select.click()
    page.locator(".q-menu .q-item").filter(has_text=re.compile(rf"^{option}$")).first.click()


def test_budgets_opens_on_realization_and_the_address_follows_the_tab(
    page: Page, base_url: str
) -> None:
    """Covers: KAL-BUD-019"""
    page.goto(f"{base_url}/budgets")
    expect(_tab(page, "Realization")).to_have_attribute("aria-selected", "true", timeout=10000)
    expect(_tab(page, "Overview")).to_have_attribute("aria-selected", "false")

    _tab(page, "Plan").click()
    expect(page).to_have_url(re.compile(r"/budgets\?tab=plan$"))
    _tab(page, "Overview").click()
    expect(page).to_have_url(re.compile(r"/budgets\?tab=overview$"))

    # A reload comes back to the tab the address names.
    page.reload()
    expect(_tab(page, "Overview")).to_have_attribute("aria-selected", "true", timeout=10000)

    page.goto(f"{base_url}/budgets?tab=plan")
    expect(_tab(page, "Plan")).to_have_attribute("aria-selected", "true", timeout=10000)

    # The old address is a 302 for its one grace release, not a 307.
    response = page.request.get(f"{base_url}/budget-plan", max_redirects=0)
    assert response.status == 302
    assert response.headers["location"] == "/budgets?tab=plan"


def test_one_month_steers_both_tabs(page: Page, base_url: str) -> None:
    """Covers: KAL-BUD-020"""
    today = datetime.date.today()
    next_year = today.year + 1
    # A month other than this one, so a change is visible whichever month it is.
    other_month = 3 if today.month != 3 else 4
    other_name = MONTHS[other_month - 1]

    page.goto(f"{base_url}/budgets")
    expect(_tab(page, "Realization")).to_have_attribute("aria-selected", "true", timeout=10000)

    year_select = page.locator("[data-period-year]")
    month_select = page.locator("[data-period-month]")
    _pick(page, year_select, str(next_year))
    _pick(page, month_select, other_name)
    expect(page.locator("[data-page-eyebrow]").first).to_contain_text(f"{other_name} {next_year}")

    # The Plan tab plans the year chosen on Realization, and its copy-forward
    # control aims at the chosen month — nothing reset by switching.
    _tab(page, "Plan").click()
    # The data attributes land on each select's focus input, which holds the
    # option's label as its value.
    expect(year_select).to_have_value(str(next_year))
    expect(month_select).to_have_value(other_name)
    plan_panel = page.locator(".q-tab-panel").filter(has=page.locator("[data-plan-cell]")).first

    def chip(year: int) -> Locator:
        return plan_panel.get_by_role("button", name=str(year), exact=True)

    on = re.compile(r"k-year-chip--on")
    expect(chip(next_year)).to_have_class(on)
    # This year was already ticked, so it stays on as a reference row under it.
    expect(chip(today.year)).to_have_class(on)
    # The copy-forward control names months short ("Mar").
    expect(plan_panel.locator(".q-select").first).to_contain_text(other_name[:3])

    # Back to this year from the page's selector, while on the Plan tab: the
    # later year can no longer be planned under it, so its chip goes off.
    _pick(page, year_select, str(today.year))
    expect(chip(next_year)).not_to_have_class(on)
    expect(chip(today.year)).to_have_class(on)

    # And the other way round: a year chip ticked on the Plan tab moves the
    # page's year, so Realization is looking at it too.
    chip(next_year).click()
    expect(year_select).to_have_value(str(next_year))
    _tab(page, "Realization").click()
    expect(page.locator("[data-page-eyebrow]").first).to_contain_text(f"{other_name} {next_year}")


def test_the_pencil_on_a_realization_row_focuses_its_plan_amount(page: Page, base_url: str) -> None:
    """Covers: KAL-BUD-021"""
    today = datetime.date.today()
    category = "Zywnosc Pencil E2E"
    cat_id = seed_category(category)
    seed_budget(cat_id, 700.0, today.month, today.year)

    page.goto(f"{base_url}/budgets")
    row = page.locator("div.k-realization-body").filter(has_text=category).last
    expect(row).to_be_visible(timeout=10000)

    pencil = row.locator("[data-edit-plan]")
    expect(pencil).to_have_attribute("aria-label", f"Edit the plan for {category}")
    pencil.click()

    expect(_tab(page, "Plan")).to_have_attribute("aria-selected", "true", timeout=5000)
    cell = page.locator(f'[data-plan-cell="{cat_id}-{today.month}"]')
    expect(cell).to_be_focused(timeout=5000)
    expect(cell).to_contain_text("700")
    # Focus, not the editor: no dialog until the user asks for one.
    expect(page.get_by_role("dialog")).to_have_count(0)

    # Enter on the focused amount is that ask.
    cell.press("Enter")
    expect(page.get_by_role("dialog")).to_be_visible(timeout=5000)


def test_alt_digits_switch_the_tabs(page: Page, base_url: str) -> None:
    """Covers: KAL-BUD-022"""
    page.goto(f"{base_url}/budgets")
    expect(_tab(page, "Realization")).to_have_attribute("aria-selected", "true", timeout=10000)
    # Keys go to the page, not to a control that might keep them.
    page.locator("body").click(position={"x": 1, "y": 1})

    page.keyboard.press("Alt+Digit3")
    expect(_tab(page, "Plan")).to_have_attribute("aria-selected", "true", timeout=5000)
    page.keyboard.press("Alt+Digit1")
    expect(_tab(page, "Overview")).to_have_attribute("aria-selected", "true", timeout=5000)
    page.keyboard.press("Alt+Digit2")
    expect(_tab(page, "Realization")).to_have_attribute("aria-selected", "true", timeout=5000)
