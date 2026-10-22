# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Budget Builder — the Apply flow.

Page URL: /wizard/budget-builder
"""

from __future__ import annotations

import datetime

from playwright.sync_api import Page, expect

from tests.e2e.seed_helpers import list_budgets, seed_category, seed_yearly_plan_variable

CURRENT_YEAR = datetime.date.today().year
APPLIED_TOAST = "Plan applied to monthly budgets."

# Hook NiceGUI's socket so the test can count the server round-trips the
# confirm button makes. Each bound click listener emits its own "event"
# message, so the number of emits on a single click is the number of times
# the plan is applied.
_HOOK_EMITS = """
() => {
  window.__emits = [];
  const s = window.socket;
  const orig = s.emit.bind(s);
  s.emit = (name, payload) => {
    if (name === 'event') window.__emits.push(payload);
    return orig(name, payload);
  };
}
"""


def test_confirm_applies_plan_once_after_reopening_diff(page: Page, base_url: str) -> None:
    """Reopening the diff before confirming still applies the plan exactly once.

    Covers: KAL-BBD-001

    In NiceGUI 3.18 ``button.on_click`` appends a listener; a single DOM click
    fires every listener the button holds. The old code re-registered the
    confirm handler on every diff open, so opening the diff twice then
    confirming once ran ``YearlyPlanService.apply`` twice (verified: two server
    round-trips from one click). The duplication was masked for a human —
    ``apply`` is an idempotent upsert and Quasar groups the two identical
    toasts into one — so the guard is the number of apply round-trips, which
    must be exactly one now that the handler is wired once at build time.
    """
    cat_id = seed_category("Groceries BBD Apply")
    # Yearly 1200 → a monthly budget row of 100.00 per category when applied.
    seed_yearly_plan_variable(CURRENT_YEAR, cat_id, "Groceries", 1200.0)

    page.goto(f"{base_url}/wizard/budget-builder")
    expect(page.get_by_text("Budget Builder", exact=True).first).to_be_visible(timeout=10000)
    page.evaluate(_HOOK_EMITS)

    apply_btn = page.get_by_role("button", name="Apply plan")
    dialog = page.locator(".q-dialog")

    # Open the diff, dismiss it, open it again — the anti-pattern's trigger.
    apply_btn.click()
    expect(dialog.get_by_text("Review changes")).to_be_visible(timeout=5000)
    dialog.get_by_role("button", name="Cancel").click()
    expect(dialog).to_be_hidden(timeout=5000)

    apply_btn.click()
    expect(dialog.get_by_text("Review changes")).to_be_visible(timeout=5000)

    # Confirm exactly once; count only the round-trips this click makes.
    page.evaluate("() => { window.__emits = []; }")
    dialog.get_by_role("button", name="Apply to budgets").click()
    expect(page.locator(".q-notification").filter(has_text=APPLIED_TOAST).first).to_be_visible(
        timeout=5000
    )
    page.wait_for_timeout(1000)
    emit_count = page.evaluate("() => window.__emits.length")
    assert emit_count == 1, (
        f"expected one apply round-trip from the confirm click, saw {emit_count}"
    )

    # The plan was applied: January holds the derived monthly row, once.
    jan = [b for b in list_budgets(CURRENT_YEAR, 1) if b["category_id"] == cat_id]
    assert len(jan) == 1, f"expected one January budget row for the category, saw {len(jan)}"
    assert str(jan[0]["amount"]) == "100.00"
