# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E test for truncated ledger cells revealing their value on hover.

Covers: KAL-TXN-019
Page URL: /transactions
"""

from __future__ import annotations

from playwright.sync_api import Page, expect

from tests.e2e.ledger import search_ledger
from tests.e2e.seed_helpers import seed_account, seed_category, seed_transaction


def test_truncated_account_cell_shows_full_name_on_hover(page: Page, base_url: str) -> None:
    """Covers: KAL-TXN-019

    The account column is a fixed 166px that truncates with an ellipsis, so a
    long account name is only legible in full through a hover tooltip.
    """
    long_account = "Bardzo Długa Nazwa Rachunku Oszczędnościowego Tooltip E2E"
    description = "Tooltip row E2E"
    account_id = seed_account(long_account)
    category_id = seed_category("Tooltip Cat E2E")
    seed_transaction(account_id, category_id, 12.34, description=description)

    page.goto(f"{base_url}/transactions")
    search_ledger(page, description)

    row = page.locator(".q-table tbody tr").filter(has_text=description)
    expect(row).to_have_count(1, timeout=10000)
    # Quasar does not render QTd's `key` prop as a DOM attribute, so the cell
    # is reached by the (fully present, only visually clipped) account text.
    account_cell = row.locator("td").filter(has_text=long_account)
    account_cell.hover()

    tooltip = page.locator(".q-tooltip").filter(has_text=long_account)
    expect(tooltip).to_be_visible(timeout=5000)

    # The description cell carries the same affordance; hovering its text
    # reveals the full description too.
    page.mouse.move(0, 0)
    desc_cell = row.locator("td").filter(has_text=description)
    desc_cell.hover()
    desc_tooltip = page.locator(".q-tooltip").filter(has_text=description)
    expect(desc_tooltip).to_be_visible(timeout=5000)
