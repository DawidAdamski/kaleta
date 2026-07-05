# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Category Management.

Covers: KAL-CAT-011

Smoke test that /categories renders the expense category tree including
the migration-seeded Subscriptions root and its children.
"""

from __future__ import annotations

from playwright.sync_api import Page, expect


def test_categories_page_renders_subscription_tree(page: Page, base_url: str) -> None:
    """Covers: KAL-CAT-011

    Opening /categories must render the Subscriptions root and its direct
    children without a server-side MissingGreenlet crash.
    """
    page.goto(f"{base_url}/categories")

    expect(page.get_by_text("Categories", exact=True).first).to_be_visible(timeout=5000)
    expect(page.get_by_text("Subscriptions", exact=True)).to_be_visible(timeout=5000)
    expect(page.get_by_text("Monthly", exact=True)).to_be_visible(timeout=5000)
    expect(page.get_by_text("Yearly", exact=True)).to_be_visible(timeout=5000)
    expect(page.get_by_text("Other", exact=True)).to_be_visible(timeout=5000)
