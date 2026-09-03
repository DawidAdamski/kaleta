# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Dashboard Customization.

Covers: KAL-DSH-001, KAL-DSH-002, KAL-DSH-003

Drives the two reset buttons in the Customize dialog against a dashboard
that has one widget switched off and one widget resized away from its
default.
"""

from __future__ import annotations

from playwright.sync_api import Page, expect

_CASHFLOW = '[data-widget-id="cashflow_chart"]'
_TREND = '[data-widget-id="net_worth_trend"]'


def _open_customize(page: Page) -> Page:
    page.get_by_role("button", name="Customize").click()
    dialog = page.get_by_role("dialog")
    expect(dialog.get_by_text("Customize Dashboard", exact=True)).to_be_visible(timeout=5000)
    return dialog


def _cycle_size(page: Page, widget_id: str) -> None:
    """Step a widget to its next allowed size, as the edit-mode resize button does."""
    applied = page.evaluate(
        """(id) => {
          if (typeof window.__kaletaCycleDashSize !== 'function') return null;
          window.__kaletaCycleDashSize(id);
          const wrap = document.querySelector('#dash-grid [data-widget-id="' + id + '"]');
          return wrap ? wrap.dataset.cols + 'x' + wrap.dataset.rows : null;
        }""",
        widget_id,
    )
    assert applied is not None, f"resize hook did not reach {widget_id}"


def test_reset_layout_then_reset_widgets(page: Page, base_url: str) -> None:
    """Covers: KAL-DSH-001, KAL-DSH-002

    Reset layout restores sizes while leaving a disabled widget disabled;
    Reset widgets brings the disabled widget back at its default size.
    """
    page.goto(f"{base_url}/")
    expect(page.locator(_CASHFLOW)).to_have_attribute("data-cols", "4", timeout=10000)

    # ── Given: net_worth_trend toggled off ────────────────────────────────
    dialog = _open_customize(page)
    dialog.locator('[data-customize-row="net_worth_trend"] .q-checkbox').click()
    dialog.get_by_role("button", name="Save").click()
    # Save closes the dialog and re-navigates to "/"; land on a settled page
    # before touching the grid.
    page.goto(f"{base_url}/")
    expect(page.locator(_CASHFLOW)).to_have_attribute("data-cols", "4", timeout=10000)
    expect(page.locator(_TREND)).to_have_count(0)

    # ── Given: cashflow_chart resized 4x2 -> 4x3 -> 2x2 ───────────────────
    _cycle_size(page, "cashflow_chart")
    _cycle_size(page, "cashflow_chart")
    expect(page.locator(_CASHFLOW)).to_have_attribute("data-cols", "2", timeout=5000)
    page.goto(f"{base_url}/")
    expect(page.locator(_CASHFLOW)).to_have_attribute("data-cols", "2", timeout=10000)
    expect(page.locator(_CASHFLOW)).to_have_attribute("data-rows", "2")
    expect(page.locator(_TREND)).to_have_count(0)

    # ── KAL-DSH-001: Reset layout ─────────────────────────────────────────
    dialog = _open_customize(page)
    dialog.get_by_role("button", name="Reset layout").click()
    # Both resets re-navigate to "/" immediately, so the confirmation toast is
    # racy to observe; the resulting grid is the assertion that matters.
    expect(page.locator(_CASHFLOW)).to_have_attribute("data-cols", "4", timeout=10000)
    expect(page.locator(_CASHFLOW)).to_have_attribute("data-rows", "2")
    # The disabled widget stays disabled — that is the whole point of the split.
    expect(page.locator(_TREND)).to_have_count(0)

    # ── KAL-DSH-002: Reset widgets ────────────────────────────────────────
    dialog = _open_customize(page)
    dialog.get_by_role("button", name="Reset widgets").click()
    expect(page.locator(_TREND)).to_have_count(1, timeout=10000)
    expect(page.locator(_TREND)).to_have_attribute("data-cols", "4")
    expect(page.locator(_TREND)).to_have_attribute("data-rows", "2")
    expect(page.locator(_CASHFLOW)).to_have_attribute("data-cols", "4")
    expect(page.locator(_CASHFLOW)).to_have_attribute("data-rows", "2")


def test_reset_layout_honours_unsaved_toggle(page: Page, base_url: str) -> None:
    """Covers: KAL-DSH-003

    Reset layout reads the live checkboxes, not the snapshot the dialog
    opened with, so a toggle made without saving first is not discarded.
    """
    page.goto(f"{base_url}/")
    expect(page.locator(_TREND)).to_have_count(1, timeout=10000)

    dialog = _open_customize(page)
    dialog.locator('[data-customize-row="net_worth_trend"] .q-checkbox').click()
    dialog.get_by_role("button", name="Reset layout").click()

    expect(page.locator(_TREND)).to_have_count(0, timeout=10000)
    expect(page.locator(_CASHFLOW)).to_have_attribute("data-cols", "4")

    # Leave the shared e2e session's dashboard back at its defaults.
    dialog = _open_customize(page)
    dialog.get_by_role("button", name="Reset widgets").click()
    expect(page.locator(_TREND)).to_have_count(1, timeout=10000)
