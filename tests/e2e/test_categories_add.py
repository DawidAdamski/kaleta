# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Category Management — the Add dialog.

Covers: KAL-CAT-013

Guards the add-subcategory flow. Presetting the dialog for a parent whose
type differs from the dialog's last-used type used to schedule a second
parent-list load (from the Type ``on_value_change`` handler) that landed
after the preset and reset the Parent select to "no parent" — so the
"subcategory" was silently saved as a top-level root. This walks the real
flow and asserts the new category lands under its parent.
"""

from __future__ import annotations

from playwright.sync_api import Page, expect


def _group_card(page: Page, name: str):
    """The Income / Expense group card, found by its heading label."""
    return page.locator(".q-card").filter(has=page.locator(".k-heading", has_text=name))


def _add_root(page: Page, group: str, name: str) -> None:
    """Add a top-level category via a group header's '+' button."""
    _group_card(page, group).get_by_role("button").first.click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible(timeout=5000)
    dialog.get_by_label("Name").fill(name)
    dialog.get_by_role("button", name="Save").click()
    expect(dialog).to_be_hidden(timeout=5000)
    expect(page.get_by_text(name, exact=True)).to_be_visible(timeout=5000)


def test_add_subcategory_lands_under_its_parent(page: Page, base_url: str) -> None:
    """Covers: KAL-CAT-013

    Add an expense root, then an income root (so the Add dialog's last type
    is Income), then add a subcategory under the expense root. The child
    must render as a subcategory of that parent, not as a new root.
    """
    page.goto(f"{base_url}/categories")
    expect(page.get_by_role("button", name="Add Category").first).to_be_visible(timeout=5000)

    # Expense root first (dialog type defaults to Expense).
    _add_root(page, "Expense", "E2E Root Exp")
    # Income root next — this flips the Add dialog's remembered type to Income.
    _add_root(page, "Income", "E2E Root Inc")

    # Add a subcategory under the EXPENSE root while the dialog's last type is
    # Income — the cross-type preset that triggered the parent-reset race.
    parent_row = page.locator(".k-cat-row").filter(has_text="E2E Root Exp")
    parent_row.get_by_role("button").first.click()  # add-subcategory button
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible(timeout=5000)
    dialog.get_by_label("Name").fill("E2E Child")
    dialog.get_by_role("button", name="Save").click()
    expect(dialog).to_be_hidden(timeout=5000)

    # The child must be a subcategory (rendered with the subcategory label),
    # not a top-level root.
    expect(page.locator(".k-subcat-label", has_text="E2E Child")).to_be_visible(timeout=5000)
