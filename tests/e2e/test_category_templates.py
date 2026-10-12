# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Category templates (the picker on the Categories page).

Covers: KAL-CTP-007

Page URL: /categories. Drives the template picker end to end: open it, tick a
template, preview the diff, apply it, and see the template's categories in the
tree. The engine itself is covered by the integration suite
(``tests/integration/test_category_templates.py``).
"""

from __future__ import annotations

from playwright.sync_api import Page, expect


def test_build_tree_from_template_picker(page: Page, base_url: str) -> None:
    """Covers: KAL-CTP-007

    Pick "Single", preview, apply — the template's "Housing" root (English, the
    e2e app's language) must then show in the category tree.
    """
    page.goto(f"{base_url}/categories")
    main = page.get_by_role("main")
    expect(main.get_by_text("Categories", exact=True).first).to_be_visible(timeout=10000)

    page.get_by_role("button", name="Load template").click()

    picker = page.get_by_role("dialog").filter(has_text="Build your tree from templates")
    expect(picker).to_be_visible(timeout=10000)
    picker.get_by_text("Single", exact=True).click()
    picker.get_by_role("button", name="Preview").click()

    preview = page.get_by_role("dialog").filter(has_text="Preview changes")
    expect(preview).to_be_visible(timeout=10000)
    expect(preview.get_by_text("Housing", exact=True)).to_be_visible(timeout=10000)
    preview.get_by_role("button", name="Apply").click()

    expect(main.get_by_text("Housing", exact=True)).to_be_visible(timeout=10000)
    expect(main.get_by_text("Rent", exact=True)).to_be_visible(timeout=10000)
