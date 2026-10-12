# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E: the annual review — the year in numbers, the carry, the commitments.

Page URL: /wizard/annual-review?year=…. The year reviewed is 2021: the shared
instance's other tests plan the current year, and the review sums every
category of the year it shows.

Covers: KAL-ANR-001, KAL-ANR-002, KAL-ANR-003
"""

from __future__ import annotations

from decimal import Decimal

from playwright.sync_api import Page, expect

from tests.e2e import seed_helpers
from tests.e2e.seed_helpers import (
    API_BASE,
    seed_budget,
    seed_category,
    seed_subscription,
)

YEAR = 2021
INSURANCE = "Insurance ANR E2E"
FOOD = "Food ANR E2E"
SUBSCRIPTION = "Gazeta ANR E2E"


def _budgets_in(year: int, category_id: int) -> Decimal:
    # The module's client, as configured with the e2e token (not a copy bound earlier).
    resp = seed_helpers._client.get(f"{API_BASE}/budgets/", params={"year": year})
    resp.raise_for_status()
    return sum(
        # ``?year=`` alone does not filter (chores.md): the year is checked here.
        (
            Decimal(b["amount"])
            for b in resp.json()
            if b["category_id"] == category_id and b["year"] == year
        ),
        Decimal("0"),
    )


def test_the_annual_review(page: Page, base_url: str) -> None:
    """Covers: KAL-ANR-001, KAL-ANR-002, KAL-ANR-003"""
    insurance = seed_category(INSURANCE)
    food = seed_category(FOOD)
    for month in range(1, 13):
        seed_budget(insurance, 100.0, month, YEAR)
        seed_budget(food, 500.0, month, YEAR)
    seed_subscription(SUBSCRIPTION, 30.0)

    page.goto(f"{base_url}/wizard/annual-review?year={YEAR}")
    # Step 1: the year in numbers.
    expect(page.get_by_test_id(f"anr-summary-{insurance}")).to_contain_text(
        "1,200.00", timeout=10000
    )
    expect(page.get_by_test_id(f"anr-summary-{food}")).to_contain_text("6,000.00")

    # Step 2: raise Insurance by 10% and carry the year over.
    pct = page.get_by_test_id(f"anr-pct-{insurance}")
    pct.fill("10")
    pct.blur()
    expect(page.get_by_test_id(f"anr-next-{insurance}")).to_have_text("1,320.00", timeout=10000)
    page.get_by_role("button", name=f"Carry into {YEAR + 1}").click()
    page.get_by_role("dialog").get_by_role("button", name="Apply to budgets").click()
    expect(page.get_by_text(f"The {YEAR + 1} budgets are set.")).to_be_visible(timeout=10000)
    assert _budgets_in(YEAR + 1, insurance) == Decimal("1320.00")
    assert _budgets_in(YEAR + 1, food) == Decimal("6000.00")

    # Step 3: each commitment asks keep / adjust / drop.
    row = page.locator('[data-testid^="anr-commitment-subscription-"]').filter(
        has_text=SUBSCRIPTION
    )
    for action in ("Keep", "Adjust", "Drop"):
        expect(row.get_by_role("button", name=action, exact=True)).to_be_visible()
    row.get_by_role("button", name="Drop", exact=True).click()
    expect(page.get_by_text(f"{SUBSCRIPTION} dropped.")).to_be_visible(timeout=10000)
    expect(row).to_have_count(0)
