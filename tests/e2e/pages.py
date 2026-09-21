# SPDX-License-Identifier: AGPL-3.0-or-later
"""Assertions that say which screen is up.

A page's own title is the thing that proves it loaded. The drawer carries
the same words as nav entries, so `get_by_text("Import")` is true on every
screen in the app — which is why these are scoped to `.k-page-title`.
"""

from __future__ import annotations

from playwright.sync_api import Page, expect


def on_import_page(page: Page) -> None:
    """The import wizard is up: its own 32px title says so.

    Scoped to `.k-page-title` rather than any element reading "Import" —
    the drawer carries that word too, and a nav entry proving the page
    loaded proves nothing.
    """
    expect(page.locator(".k-page-title")).to_have_text("Import", timeout=5000)
