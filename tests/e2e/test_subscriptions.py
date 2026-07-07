# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Subscriptions Panel.

Page URL: /wizard/subscriptions
"""

from __future__ import annotations

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
    expect(page.get_by_text("Subscriptions", exact=True).first).to_be_visible(timeout=5000)

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
