# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E: the rate list shows the instance's NBP rates beside the family's own.

Covers: KAL-FXR-004

Page URL: /settings (Data tab)
"""

from __future__ import annotations

import datetime
from collections.abc import Generator

import pytest
from playwright.sync_api import Page, expect

from tests.e2e import seed_helpers as sh

# Literals from KAL-FXR-004.
JULY_19 = datetime.date(2024, 7, 19)
JULY_22 = datetime.date(2024, 7, 22)


@pytest.fixture
def euro_rates() -> Generator[None]:
    """A EUR account, the family's own EUR→PLN rate and an NBP mid; all gone afterwards."""
    account = sh.seed_account("NBP rates e2e (EUR)", currency="EUR")
    own = sh.seed_family_rate(JULY_19, "EUR", "PLN", "4.1000")
    sh.seed_nbp_rate(JULY_22, "EUR", "4.2500")
    try:
        yield
    finally:
        sh.delete_nbp_rates()
        sh.delete_family_rate(own)
        sh.delete_account(account)


def test_an_nbp_rate_is_listed_as_the_instances_and_cannot_be_deleted(
    page: Page, base_url: str, euro_rates: None
) -> None:
    """Covers: KAL-FXR-004"""
    page.goto(f"{base_url}/settings")
    page.get_by_role("tab", name="Data").click()

    nbp_row = page.locator("tr").filter(has_text="2024-07-22").filter(has_text="EUR = ? PLN")
    own_row = page.locator("tr").filter(has_text="2024-07-19").filter(has_text="EUR = ? PLN")
    expect(nbp_row).to_contain_text("NBP", timeout=10000)
    expect(nbp_row).to_contain_text("4.250000")
    expect(own_row).to_contain_text("Yours")
    expect(own_row).to_contain_text("4.100000")

    expect(own_row.locator("i", has_text="delete")).to_have_count(1)
    expect(nbp_row.locator("i", has_text="delete")).to_have_count(0)
