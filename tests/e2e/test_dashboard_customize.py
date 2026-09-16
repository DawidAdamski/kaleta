# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Dashboard Customization.

Covers: KAL-DSH-001, KAL-DSH-002, KAL-DSH-003, KAL-DSH-004

Drives the two reset buttons in the Customize dialog against a dashboard
that has one widget switched off and one widget resized away from its
default.
"""

from __future__ import annotations

from playwright.sync_api import Page, expect

_CASHFLOW = '[data-widget-id="cashflow_chart"]'
_TREND = '[data-widget-id="net_worth_trend"]'
_BALANCE = '[data-widget-id="balance_card"]'
_MONTH = '[data-widget-id="month_card"]'

#: The seven single-figure KPI widgets a pre-restyle profile still stores.
_LEGACY_KPIS = (
    "total_balance",
    "month_income",
    "month_expenses",
    "month_net",
    "predicted_30d",
    "net_worth",
    "savings_rate_kpi",
)


def _open_customize(page: Page) -> Page:
    page.get_by_role("button", name="Customize").click()
    dialog = page.get_by_role("dialog")
    expect(dialog.get_by_text("Customize Dashboard", exact=True)).to_be_visible(timeout=5000)
    return dialog


def _wait_for_grid_settled(page: Page) -> None:
    """Block until NiceGUI has finished streaming widgets into ``#dash-grid``.

    Widgets arrive one at a time over the websocket. Resizing before the grid
    is complete is a race in two ways: Vue re-patches the container on each
    arrival, undoing the raw ``data-cols`` write ``__kaletaCycleDashSize``
    performs, and ``__kaletaPostDashLayout`` serialises *whatever is in the
    DOM right now* — so a POST fired mid-stream persists a layout that is
    missing every widget yet to arrive. The window widens with each widget
    added to the default dashboard, so wait for the child count to hold
    steady rather than guessing at a sleep.
    """
    page.wait_for_function(
        """() => {
          const grid = document.getElementById('dash-grid');
          if (!grid) return false;
          const n = grid.querySelectorAll('[data-widget-id]').length;
          const s = window.__kaletaGridSettle || {count: -1, stable: 0};
          s.stable = n > 0 && n === s.count ? s.stable + 1 : 0;
          s.count = n;
          window.__kaletaGridSettle = s;
          return s.stable >= 3;
        }""",
        polling=200,
        timeout=30000,
    )


def _cycle_size(page: Page, widget_id: str) -> str:
    """Step a widget to its next allowed size, as the edit-mode resize button does.

    Waits for the layout POST the hook fires. It is a fire-and-forget
    ``fetch``, so navigating away before it lands aborts it and the new size
    is silently never persisted — the failure then only shows up after the
    next page load, far from its cause.
    """
    with page.expect_response("**/_dashboard/layout") as response_info:
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
    assert response_info.value.ok, "layout POST did not succeed"
    return str(applied)


def _post_layout(page: Page, entries: list[dict[str, object]]) -> None:
    """Persist *entries* through the same endpoint the drag handler posts to."""
    with page.expect_response("**/_dashboard/layout") as response_info:
        page.evaluate(
            """(entries) => fetch('/_dashboard/layout', {
              method: 'POST',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({entries}),
            })""",
            entries,
        )
    assert response_info.value.ok, "layout POST did not succeed"


def test_reset_layout_then_reset_widgets(page: Page, base_url: str) -> None:
    """Covers: KAL-DSH-001, KAL-DSH-002

    Reset layout restores sizes while leaving a disabled widget disabled;
    Reset widgets brings the disabled widget back at its default size.
    """
    page.goto(f"{base_url}/")
    _wait_for_grid_settled(page)
    expect(page.locator(_CASHFLOW)).to_have_attribute("data-cols", "4", timeout=10000)

    # ── Given: net_worth_trend toggled off ────────────────────────────────
    dialog = _open_customize(page)
    dialog.locator('[data-customize-row="net_worth_trend"] .q-checkbox').click()
    # Save closes the dialog and re-navigates to "/" itself. Racing it with an
    # explicit goto aborts whichever load loses (net::ERR_ABORTED); wait for
    # the navigation Save starts, then let the grid settle.
    with page.expect_navigation(wait_until="load", timeout=15000):
        dialog.get_by_role("button", name="Save").click()
    _wait_for_grid_settled(page)
    expect(page.locator(_CASHFLOW)).to_have_attribute("data-cols", "4", timeout=10000)
    expect(page.locator(_TREND)).to_have_count(0)

    # ── Given: cashflow_chart resized 4x2 -> 4x3 -> 2x2 ───────────────────
    assert _cycle_size(page, "cashflow_chart") == "4x3"
    assert _cycle_size(page, "cashflow_chart") == "2x2"
    expect(page.locator(_CASHFLOW)).to_have_attribute("data-cols", "2", timeout=5000)
    page.goto(f"{base_url}/")
    _wait_for_grid_settled(page)
    expect(page.locator(_CASHFLOW)).to_have_attribute("data-cols", "2", timeout=10000)
    expect(page.locator(_CASHFLOW)).to_have_attribute("data-rows", "2")
    expect(page.locator(_TREND)).to_have_count(0)

    # ── KAL-DSH-001: Reset layout ─────────────────────────────────────────
    dialog = _open_customize(page)
    dialog.get_by_role("button", name="Reset layout").click()
    # Both resets re-navigate to "/" immediately, so the confirmation toast is
    # racy to observe; the resulting grid is the assertion that matters.
    _wait_for_grid_settled(page)
    expect(page.locator(_CASHFLOW)).to_have_attribute("data-cols", "4", timeout=10000)
    expect(page.locator(_CASHFLOW)).to_have_attribute("data-rows", "2")
    # The disabled widget stays disabled — that is the whole point of the split.
    expect(page.locator(_TREND)).to_have_count(0)

    # ── KAL-DSH-002: Reset widgets ────────────────────────────────────────
    dialog = _open_customize(page)
    dialog.get_by_role("button", name="Reset widgets").click()
    _wait_for_grid_settled(page)
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
    _wait_for_grid_settled(page)
    expect(page.locator(_TREND)).to_have_count(1, timeout=10000)

    dialog = _open_customize(page)
    dialog.locator('[data-customize-row="net_worth_trend"] .q-checkbox').click()
    dialog.get_by_role("button", name="Reset layout").click()

    _wait_for_grid_settled(page)
    expect(page.locator(_TREND)).to_have_count(0, timeout=10000)
    expect(page.locator(_CASHFLOW)).to_have_attribute("data-cols", "4")

    # Leave the shared e2e session's dashboard back at its defaults.
    dialog = _open_customize(page)
    dialog.get_by_role("button", name="Reset widgets").click()
    _wait_for_grid_settled(page)
    expect(page.locator(_TREND)).to_have_count(1, timeout=10000)


def test_legacy_kpi_layout_migrates_to_merged_cards(page: Page, base_url: str) -> None:
    """Covers: KAL-DSH-004

    Stores the pre-restyle layout — the seven single-figure KPI widgets —
    straight through the layout endpoint, then loads the dashboard twice:
    once to see them replaced by the two merged cards in the position the
    first of them held, once to prove the migration does not stack up.
    """
    page.goto(f"{base_url}/")
    _wait_for_grid_settled(page)

    # ── Given: the seven KPI widgets, with a chart sitting in front ───────
    legacy = [{"id": wid, "cols": 2, "rows": 1} for wid in _LEGACY_KPIS]
    _post_layout(page, [{"id": "cashflow_chart", "cols": 4, "rows": 2}, *legacy])

    # ── When: the dashboard loads ─────────────────────────────────────────
    page.goto(f"{base_url}/")
    _wait_for_grid_settled(page)

    # ── Then: the merged cards are there and the seven are not ────────────
    expect(page.locator(_BALANCE)).to_have_count(1, timeout=10000)
    expect(page.locator(_MONTH)).to_have_count(1)
    for wid in _LEGACY_KPIS:
        expect(page.locator(f'[data-widget-id="{wid}"]')).to_have_count(0)

    # ── And: they took the first KPI widget's place, behind the chart ─────
    order = page.locator("#dash-grid [data-widget-id]").evaluate_all(
        "els => els.map(e => e.dataset.widgetId)"
    )
    assert order == ["cashflow_chart", "balance_card", "month_card"], order

    # ── And: a second load does not add a second copy ─────────────────────
    page.goto(f"{base_url}/")
    _wait_for_grid_settled(page)
    expect(page.locator(_BALANCE)).to_have_count(1, timeout=10000)
    expect(page.locator(_MONTH)).to_have_count(1)

    # Leave the shared e2e session's dashboard back at its defaults.
    dialog = _open_customize(page)
    dialog.get_by_role("button", name="Reset widgets").click()
    _wait_for_grid_settled(page)
    expect(page.locator(_TREND)).to_have_count(1, timeout=10000)
