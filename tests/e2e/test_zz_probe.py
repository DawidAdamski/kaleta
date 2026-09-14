# SPDX-License-Identifier: AGPL-3.0-or-later
"""Temporary DOM probe."""

from __future__ import annotations

from playwright.sync_api import Page


def test_probe(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/forecast")
    page.wait_for_timeout(4000)
    out = page.evaluate(
        "() => Array.from(document.querySelectorAll('.q-select')).map("
        "e => e.outerHTML.slice(0, 260))"
    )
    print("PROBE_SELECTS", out)
    labels = page.evaluate(
        "() => Array.from(document.querySelectorAll('[aria-label]')).map("
        "e => e.tagName + '|' + e.getAttribute('aria-label'))"
    )
    print("PROBE_ARIA", labels)
