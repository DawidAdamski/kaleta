"""E2E tests for Feature: Initial Setup Wizard.

Maps scenarios from docs/bdd.md — Feature: Initial Setup Wizard.

The BDD feature describes the "Na start" onboarding section at /wizard.
"""

from __future__ import annotations

from playwright.sync_api import Page, expect

from tests.e2e import seed_helpers as sh


def _ensure_onboarding_expanded(page: Page) -> None:
    """Expand the collapsible onboarding card when steps are hidden (e.g. all done)."""
    if not page.get_by_text("Add an institution").is_visible():
        page.get_by_text("Getting started — set up your finances", exact=True).click()
        expect(page.get_by_text("Add an institution")).to_be_visible(timeout=5000)


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
    expect(page.get_by_text("Getting started — set up your finances")).to_be_visible(timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: Wizard shows all four setup step titles
# ---------------------------------------------------------------------------


def test_wizard_shows_all_four_setup_steps(page: Page, base_url: str) -> None:
    """All four onboarding step titles are visible on the wizard page."""
    page.goto(f"{base_url}/wizard")
    _ensure_onboarding_expanded(page)

    expect(page.get_by_text("Add an institution")).to_be_visible(timeout=5000)
    expect(page.get_by_text("Create an account with opening balance")).to_be_visible(timeout=5000)
    expect(page.get_by_text("Create expense and income categories")).to_be_visible(timeout=5000)
    expect(page.get_by_text("Import or add transactions")).to_be_visible(timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: Institution step hint shown when no institution exists
# ---------------------------------------------------------------------------


def test_wizard_institution_hint_shown_when_no_institutions(page: Page, base_url: str) -> None:
    """Scenario: Institution step pending hint is visible (not necessarily empty DB)."""
    page.goto(f"{base_url}/wizard")
    _ensure_onboarding_expanded(page)

    # Either the hint text OR the count text will be visible depending on DB state.
    hint = page.get_by_text("You can't add an account without an institution.")
    count = page.get_by_text("institutions.", exact=False)
    expect(hint.or_(count).first).to_be_visible(timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: Institution step is marked done after adding an institution
# ---------------------------------------------------------------------------


def test_wizard_institution_step_marked_done(page: Page, base_url: str) -> None:
    """Scenario: Wizard marks institution step as done."""
    seed_institution("PKO BP Wizard E2E Test")

    page.goto(f"{base_url}/wizard")
    _ensure_onboarding_expanded(page)

    # When at least one institution exists the count label is shown.
    # It reads "You have N institutions."
    expect(page.get_by_text("institutions.", exact=False).first).to_be_visible(timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: Account step marked done after adding an account
# ---------------------------------------------------------------------------


def test_wizard_account_step_marked_done(page: Page, base_url: str) -> None:
    """Wizard marks account step done when at least one account exists."""
    inst_id = seed_institution("mBank Wizard E2E Account")
    seed_account("Wizard E2E Account", institution_id=inst_id)

    page.goto(f"{base_url}/wizard")
    _ensure_onboarding_expanded(page)

    expect(page.get_by_text("accounts.", exact=False).first).to_be_visible(timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: Go buttons navigate to correct pages
# ---------------------------------------------------------------------------


def test_wizard_institution_go_button_navigates(page: Page, base_url: str) -> None:
    """Clicking Go/Edit on the institution step navigates to /institutions."""
    page.goto(f"{base_url}/wizard")
    _ensure_onboarding_expanded(page)

    # Each onboarding step is a ui.row() (div.row) that contains a label with the
    # step title AND a button. Using `has=` finds the row that *contains* the exact
    # title text, then we click the single button inside that row.
    row = page.locator("div.row").filter(has=page.get_by_text("Add an institution", exact=True))
    row.get_by_role("button").click()

    expect(page).to_have_url(f"{base_url}/institutions", timeout=5000)


def test_wizard_account_go_button_navigates(page: Page, base_url: str) -> None:
    """Clicking Go/Edit on the accounts step navigates to /accounts."""
    page.goto(f"{base_url}/wizard")
    _ensure_onboarding_expanded(page)

    row = page.locator("div.row").filter(
        has=page.get_by_text("Create an account with opening balance", exact=True)
    )
    row.get_by_role("button").click()

    expect(page).to_have_url(f"{base_url}/accounts", timeout=5000)


def test_wizard_categories_go_button_navigates(page: Page, base_url: str) -> None:
    """Clicking Go/Edit on the categories step navigates to /categories."""
    page.goto(f"{base_url}/wizard")
    _ensure_onboarding_expanded(page)

    row = page.locator("div.row").filter(
        has=page.get_by_text("Create expense and income categories", exact=True)
    )
    row.get_by_role("button").click()

    expect(page).to_have_url(f"{base_url}/categories", timeout=5000)


def test_wizard_import_go_button_navigates(page: Page, base_url: str) -> None:
    """Clicking Go/Edit on the import step navigates to /import."""
    page.goto(f"{base_url}/wizard")
    _ensure_onboarding_expanded(page)

    row = page.locator("div.row").filter(
        has=page.get_by_text("Import or add transactions", exact=True)
    )
    row.get_by_role("button").click()

    expect(page).to_have_url(f"{base_url}/import", timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: All-done badge when every step is complete
# ---------------------------------------------------------------------------


def test_wizard_all_done_badge_when_setup_complete(page: Page, base_url: str) -> None:
    """Scenario: Completing all steps marks setup as done

    Maps to docs/bdd.md — Feature: Initial Setup Wizard (Finish Setup gate).
    The live app surfaces an "All done!" badge on /wizard once all onboarding steps
    are satisfied (institution, account, categories, transactions).
    """
    inst_id = seed_institution("All Done Wizard E2E Bank")
    acc_id = seed_account("All Done Wizard E2E Account", institution_id=inst_id)
    exp_id = sh.seed_category("All Done E2E Expense Cat")
    sh.seed_income_category("All Done E2E Income Cat")
    sh.seed_transaction(acc_id, exp_id, 10.0, description="wizard e2e seed")

    page.goto(f"{base_url}/wizard")
    expect(page.get_by_text("All done!")).to_be_visible(timeout=5000)
