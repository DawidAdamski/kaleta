# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E for Feature: Settings — one example-data panel.

Covers: KAL-SET-033

Page URL: /settings (Data tab)

Seeding lives in a single "Example data" card: the additive per-feature buttons
and "Seed everything", plus the one destructive "Populate with example data"
(wipe + reseed) below them. The old separate "Demo data" card is gone.

This test never *runs* the wipe+reseed — that would clear the shared e2e
worker's data out from under every other test. It opens the confirm dialog and
cancels, like the data-safety test does for Clear.
"""

from __future__ import annotations

from playwright.sync_api import Page, expect


def _open_data_tab(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/settings")
    page.get_by_role("tab", name="Data").click()


def test_seeding_lives_in_one_example_data_card(page: Page, base_url: str) -> None:
    """Covers: KAL-SET-033"""
    _open_data_tab(page, base_url)

    example_card = page.locator(".q-card").filter(has_text="Example data").first
    expect(example_card).to_be_visible(timeout=5000)

    # Both the additive "Seed everything" and the destructive reset live in it.
    expect(example_card.get_by_role("button", name="Seed everything")).to_be_visible()
    reset_btn = example_card.get_by_role("button", name="Populate with example data")
    expect(reset_btn.first).to_be_visible()

    # The old separate "Demo data" card is gone — one place for example data.
    expect(page.get_by_text("Demo data", exact=True)).to_have_count(0)

    # The reset is a confirmed, destructive action; open it and cancel without
    # running it (it would wipe the shared worker DB).
    reset_btn.first.click()
    dialog = page.get_by_role("dialog")
    expect(dialog.get_by_text("Populate with example data?", exact=True)).to_be_visible(
        timeout=5000
    )
    dialog.get_by_role("button", name="Cancel").click()


def test_clear_all_data_moved_beside_backups(page: Page, base_url: str) -> None:
    """Covers: KAL-SET-033"""
    _open_data_tab(page, base_url)

    backups_card = page.locator(".q-card").filter(has_text="Backups & clearing").first
    expect(backups_card).to_be_visible(timeout=5000)
    expect(backups_card.get_by_role("button", name="Clear all data")).to_be_visible()
