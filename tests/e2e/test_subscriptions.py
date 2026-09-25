# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Subscriptions Panel.

Page URL: /wizard/subscriptions
"""

from __future__ import annotations

import datetime
import re

from playwright.sync_api import Page, expect

from tests.e2e.seed_helpers import (
    seed_account,
    seed_category,
    seed_recurring_payee_charges,
    seed_subscription,
)


def test_subscriptions_listed_with_cadence_and_price(page: Page, base_url: str) -> None:
    """Covers: KAL-SUB-001

    Subscriptions panel lists each subscription with its price and billing cadence.
    """
    seed_subscription("Netflix SUB E2E", 49.99, cadence_days=30)
    seed_subscription("Domain SUB E2E", 120.00, cadence_days=365)

    page.goto(f"{base_url}/wizard/subscriptions")
    expect(page.get_by_role("main").get_by_text("Subscriptions", exact=True).first).to_be_visible(
        timeout=5000
    )

    active_section = page.locator(".q-card").filter(has_text="All subscriptions")
    expect(active_section.get_by_text("Netflix SUB E2E", exact=True).first).to_be_visible(
        timeout=5000
    )
    expect(active_section.get_by_text("Domain SUB E2E", exact=True).first).to_be_visible(
        timeout=5000
    )
    expect(active_section.get_by_text("49.99").first).to_be_visible(timeout=5000)
    expect(active_section.get_by_text("120.00").first).to_be_visible(timeout=5000)
    expect(page.get_by_text(re.compile(r"Netflix SUB E2E.*Monthly"))).to_be_visible(timeout=5000)
    expect(page.get_by_text(re.compile(r"Domain SUB E2E.*Yearly"))).to_be_visible(timeout=5000)


def test_track_detected_recurring_payment_as_subscription(page: Page, base_url: str) -> None:
    """Covers: KAL-SUB-003

    A detected recurring payment can be confirmed from the detector and appears
    in the subscriptions list.
    """
    account_id = seed_account("SUB Detect E2E")
    category_id = seed_category("SUB Streaming E2E")
    seed_recurring_payee_charges(
        account_id,
        category_id,
        "Spotify SUB E2E",
        23.99,
        months=3,
    )

    page.goto(f"{base_url}/wizard/subscriptions")
    expect(page.get_by_text("Detected recurring charges", exact=True)).to_be_visible(timeout=5000)

    spotify_row = page.locator(".q-card").filter(has_text="Spotify SUB E2E")
    expect(spotify_row.get_by_text("Spotify SUB E2E", exact=True)).to_be_visible(timeout=5000)
    spotify_row.get_by_role("button", name="Track").click()

    confirm = page.get_by_role("dialog")
    if confirm.get_by_text("Track as a subscription", exact=True).is_visible(timeout=2000):
        confirm.get_by_role("button", name="Track").click()

    expect(page.get_by_text("Spotify SUB E2E", exact=True)).to_be_visible(timeout=5000)
    expect(page.get_by_text("23.99").first).to_be_visible(timeout=5000)


def test_stable_monthly_payment_is_detected(page: Page, base_url: str) -> None:
    """Covers: KAL-REC-001

    Three consecutive months of a 49.99 payment to "Netflix" are listed in
    the Subscriptions panel's detected recurring charges as monthly, 49.99.
    """
    account_id = seed_account("REC Detect E2E")
    category_id = seed_category("REC Streaming E2E")
    seed_recurring_payee_charges(account_id, category_id, "Netflix", 49.99, months=3)

    page.goto(f"{base_url}/wizard/subscriptions")
    detector = page.locator(".q-card").filter(has_text="Detected recurring charges")
    expect(detector).to_be_visible(timeout=5000)

    netflix_row = detector.locator(".nicegui-row").filter(
        has=page.get_by_text("Netflix", exact=True)
    )
    expect(netflix_row).to_have_count(1, timeout=5000)
    expect(netflix_row).to_contain_text("Monthly")
    expect(netflix_row).to_contain_text("49.99")


def _open_cancel_dialog(page: Page, base_url: str, name: str) -> None:
    page.goto(f"{base_url}/wizard/subscriptions")
    current = page.locator(".q-card").filter(has_text="All subscriptions")
    row = current.locator(".nicegui-row").filter(has=page.get_by_text(name, exact=True)).last
    expect(row).to_be_visible(timeout=5000)
    # Icon-only button: Quasar marks the icon aria-hidden, so match the glyph.
    row.locator("button").filter(
        has=page.locator(".q-icon", has_text=re.compile(r"^cancel$"))
    ).click()
    expect(page.get_by_text("Cancelled as of").first).to_be_visible(timeout=5000)


def test_cancel_as_of_today_moves_row_to_cancelled_section(page: Page, base_url: str) -> None:
    """Covers: KAL-SUB-004

    Once the cancellation date has come, the subscription moves to the
    cancelled section below the active list.
    """
    seed_subscription("Netflix SUB004 E2E", 49.99, cadence_days=30)

    _open_cancel_dialog(page, base_url, "Netflix SUB004 E2E")
    page.get_by_role("dialog").get_by_role("button", name="Cancel subscription").click()

    cancelled = page.locator(".q-card").filter(
        has=page.locator(".k-heading", has_text=re.compile(r"^Cancelled$"))
    )
    expect(cancelled.get_by_text("Netflix SUB004 E2E", exact=True)).to_be_visible(timeout=5000)
    current = page.locator(".q-card").filter(has_text="All subscriptions")
    expect(current.get_by_text("Netflix SUB004 E2E", exact=True)).to_have_count(0)


def test_cancel_as_of_future_date_keeps_row_active(page: Page, base_url: str) -> None:
    """Covers: KAL-SUB-004

    Until the cancellation date the subscription stays in the active list.
    """
    seed_subscription("Domain SUB004 E2E", 49.99, cadence_days=30)
    effective_on = datetime.date.today() + datetime.timedelta(days=10)

    _open_cancel_dialog(page, base_url, "Domain SUB004 E2E")
    dialog = page.get_by_role("dialog")
    dialog.get_by_label("Cancelled as of").fill(effective_on.isoformat())
    dialog.get_by_role("button", name="Cancel subscription").click()

    current = page.locator(".q-card").filter(has_text="All subscriptions")
    expect(current.get_by_text(f"Cancels {effective_on.strftime('%d.%m.%Y')}").first).to_be_visible(
        timeout=5000
    )
    expect(current.get_by_text("Domain SUB004 E2E", exact=True)).to_be_visible(timeout=5000)
