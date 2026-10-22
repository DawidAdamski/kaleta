# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E: the recent-transactions card signs a transfer leg by its direction.

Covers: KAL-DSH-011

The dashboard reads the same money as the ledger, so a transfer's incoming
leg must read positive here too (KAL-TRF-005 fixed the ledger). Signed from
the type alone, both legs showed negative. A transfer stays neutral in colour
whichever way it went.
"""

from __future__ import annotations

import datetime

from playwright.sync_api import Page, expect

from tests.e2e.seed_helpers import (
    delete_account,
    delete_transaction,
    get_or_seed_category,
    seed_account,
    seed_transaction,
)

DESKTOP = {"width": 1360, "height": 900}


def _open_desktop_dashboard(page: Page, base_url: str) -> None:
    page.set_viewport_size(DESKTOP)
    page.goto(f"{base_url}/")
    page.wait_for_function("() => window.did_handshake === true", timeout=20000)


def _wait_for_grid_settled(page: Page) -> None:
    """Block until NiceGUI has finished streaming widgets into ``#dash-grid``."""
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


def test_recent_card_signs_a_transfer_leg_by_direction(page: Page, base_url: str) -> None:
    """Covers: KAL-DSH-011"""
    today = datetime.date.today()
    out_acc = seed_account("mBank DSH11 E2E")
    in_acc = seed_account("PKO BP DSH11 E2E")
    cat = get_or_seed_category("Przelew DSH11 E2E")
    # Two non-internal transfer legs (not a recognised internal pair, which the
    # card filters out). Unlinked, so each deletes cleanly in teardown — a
    # mutual ``linked_transaction_id`` would block the raw delete. Dated today
    # so they sit at the top of the ten most-recent rows.
    out_id = seed_transaction(
        out_acc, cat, 500.00, tx_type="transfer", date=today, description="DSH11 leaving"
    )
    in_id = seed_transaction(
        in_acc,
        cat,
        500.00,
        tx_type="transfer",
        date=today,
        description="DSH11 arriving",
        transfer_direction="in",
    )
    try:
        _open_desktop_dashboard(page, base_url)
        _wait_for_grid_settled(page)

        card = page.locator('[data-widget-id="recent_transactions"]')
        expect(card.locator(".k-dash-card")).to_be_visible(timeout=10000)

        out_row = card.locator("tr").filter(has_text="DSH11 leaving")
        in_row = card.locator("tr").filter(has_text="DSH11 arriving")
        # Money leaving reads negative; money arriving reads positive — the
        # whole point of signing by direction rather than by type.
        expect(out_row.locator("span.k-amount")).to_have_text("-500.00", timeout=10000)
        expect(in_row.locator("span.k-amount")).to_have_text("+500.00", timeout=10000)
        # Colour follows the raw type: a transfer leg is neutral either way.
        expect(in_row.locator("span.k-amount")).to_have_class("k-amount k-amount--neutral")
    finally:
        delete_transaction(out_id)
        delete_transaction(in_id)
        delete_account(out_acc)
        delete_account(in_acc)
