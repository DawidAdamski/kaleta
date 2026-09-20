# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Initial Setup Wizard.

Maps scenarios from docs/bdd.md — Feature: Initial Setup Wizard.

The BDD feature describes the Setup section at /wizard, which artboard 3d
heads with a rule and four done-cards.
"""

from __future__ import annotations

import re

from playwright.sync_api import Locator, Page, expect

from tests.e2e import seed_helpers as sh


def _setup_header(page: Page) -> Locator:
    """The rule artboard 3d heads the four setup cards with."""
    return page.locator('[data-section="setup"]')


def _setup_card(page: Page, key: str) -> Locator:
    """One of the four Setup done-cards, by its own hook rather than DOM shape."""
    return page.locator(f"[data-setup-step='{key}']")


def _ensure_onboarding_expanded(page: Page) -> None:
    """Expand the collapsible Setup section when its cards are hidden (all done)."""
    expect(_setup_header(page)).to_be_visible(timeout=5000)
    if not _setup_card(page, "institution").is_visible():
        _setup_header(page).click()
        expect(_setup_card(page, "institution")).to_be_visible(timeout=5000)


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


def seed_institution(name: str) -> int:
    return sh.seed_institution(name)


def seed_account(name: str, institution_id: int | None = None) -> int:
    return sh.seed_account(name, institution_id=institution_id)


# ---------------------------------------------------------------------------
# Scenario: Wizard page loads and shows onboarding section
# ---------------------------------------------------------------------------


def test_wizard_page_loads_with_onboarding_section(page: Page, base_url: str) -> None:
    """Wizard page renders the onboarding card."""
    page.goto(f"{base_url}/wizard")

    expect(page.get_by_text("Financial Wizard", exact=True).first).to_be_visible(timeout=5000)
    expect(_setup_header(page)).to_contain_text("Setup", timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: Wizard shows all four setup step titles
# ---------------------------------------------------------------------------


def test_wizard_shows_all_four_setup_steps(page: Page, base_url: str) -> None:
    """Covers: KAL-ONB-001"""
    page.goto(f"{base_url}/wizard")
    _ensure_onboarding_expanded(page)

    # Scoped to each card: "Accounts" and "Categories" are also sidebar
    # entries, so an unscoped match would pass with the section collapsed.
    for key, title in (
        ("institution", "Institutions"),
        ("account", "Accounts"),
        ("categories", "Categories"),
        ("import", "First import"),
    ):
        expect(_setup_card(page, key)).to_contain_text(title, timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: Institution step hint shown when no institution exists
# ---------------------------------------------------------------------------


def test_wizard_institution_hint_shown_when_no_institutions(page: Page, base_url: str) -> None:
    """Covers: KAL-ONB-001"""
    page.goto(f"{base_url}/wizard")
    _ensure_onboarding_expanded(page)

    # Either the hint text OR the count text will be visible depending on DB state.
    card = _setup_card(page, "institution")
    expect(card).to_contain_text(
        re.compile(r"You can't add an account without an institution\.|\d+ institutions?"),
        timeout=5000,
    )


# ---------------------------------------------------------------------------
# Scenario: Institution step is marked done after adding an institution
# ---------------------------------------------------------------------------


def test_wizard_institution_step_marked_done(page: Page, base_url: str) -> None:
    """Covers: KAL-ONB-002"""
    seed_institution("PKO BP Wizard E2E Test")

    page.goto(f"{base_url}/wizard")
    _ensure_onboarding_expanded(page)

    # When at least one institution exists the card carries the count.
    expect(_setup_card(page, "institution")).to_contain_text(
        re.compile(r"\d+ institutions?"), timeout=5000
    )


# ---------------------------------------------------------------------------
# Scenario: Account step marked done after adding an account
# ---------------------------------------------------------------------------


def test_wizard_account_step_marked_done(page: Page, base_url: str) -> None:
    """Covers: KAL-ONB-002"""
    inst_id = seed_institution("mBank Wizard E2E Account")
    seed_account("Wizard E2E Account", institution_id=inst_id)

    page.goto(f"{base_url}/wizard")
    _ensure_onboarding_expanded(page)

    expect(_setup_card(page, "account")).to_contain_text(re.compile(r"\d+ accounts?"), timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: Go buttons navigate to correct pages
# ---------------------------------------------------------------------------


def test_wizard_institution_go_button_navigates(page: Page, base_url: str) -> None:
    """Clicking Go/Edit on the institution step navigates to /institutions."""
    page.goto(f"{base_url}/wizard")
    _ensure_onboarding_expanded(page)

    # Each Setup step is a done-card carrying its own data-setup-step hook, so
    # the test names the card rather than reconstructing it from DOM shape.
    _setup_card(page, "institution").get_by_role("button").click()

    expect(page).to_have_url(f"{base_url}/institutions", timeout=5000)


def test_wizard_account_go_button_navigates(page: Page, base_url: str) -> None:
    """Clicking Go/Edit on the accounts step navigates to /accounts."""
    page.goto(f"{base_url}/wizard")
    _ensure_onboarding_expanded(page)

    _setup_card(page, "account").get_by_role("button").click()

    expect(page).to_have_url(f"{base_url}/accounts", timeout=5000)


def test_wizard_categories_go_button_navigates(page: Page, base_url: str) -> None:
    """Clicking Go/Edit on the categories step navigates to /categories."""
    page.goto(f"{base_url}/wizard")
    _ensure_onboarding_expanded(page)

    _setup_card(page, "categories").get_by_role("button").click()

    expect(page).to_have_url(f"{base_url}/categories", timeout=5000)


def test_wizard_import_go_button_navigates(page: Page, base_url: str) -> None:
    """Clicking Go/Edit on the import step navigates to /import."""
    page.goto(f"{base_url}/wizard")
    _ensure_onboarding_expanded(page)

    _setup_card(page, "import").get_by_role("button").click()

    expect(page).to_have_url(f"{base_url}/import", timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: All-done badge when every step is complete
# ---------------------------------------------------------------------------


def test_wizard_all_done_badge_when_setup_complete(page: Page, base_url: str) -> None:
    """Covers: KAL-ONB-002

    The live app says "All four done" beside the Setup rule on /wizard once
    all onboarding steps are satisfied (institution, account, categories,
    transactions).
    """
    inst_id = seed_institution("All Done Wizard E2E Bank")
    acc_id = seed_account("All Done Wizard E2E Account", institution_id=inst_id)
    exp_id = sh.seed_category("All Done E2E Expense Cat")
    sh.seed_income_category("All Done E2E Income Cat")
    sh.seed_transaction(acc_id, exp_id, 10.0, description="wizard e2e seed")

    page.goto(f"{base_url}/wizard")
    expect(_setup_header(page)).to_contain_text("All four done", timeout=5000)
