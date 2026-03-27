"""E2E tests for Feature: Credit Calculator.

Maps scenarios from docs/bdd.md — Feature: Credit Calculator.
Page URL: /credit-calculator

The credit calculator is a pure client-side computation page — no seeding
required. All scenarios drive the form inputs and assert on the rendered
result cards.
"""
from __future__ import annotations

from playwright.sync_api import Page, expect

BASE_URL = "http://localhost:8080"


def _fill_number(page: Page, label: str, value: str) -> None:
    """Select-all then type into a NiceGUI number field."""
    field = page.get_by_label(label)
    field.click(click_count=3)
    field.fill(value)


# ---------------------------------------------------------------------------
# Scenario: Calculate a standard consumer loan with equal installments
# ---------------------------------------------------------------------------

def test_calculate_consumer_loan_equal_installments(page: Page) -> None:
    """Scenario: Calculate a standard consumer loan with equal installments"""
    page.goto(f"{BASE_URL}/credit-calculator")

    page.locator(".q-select").filter(has_text="Payment Type").click()
    page.get_by_role("option", name="Equal installments (annuity)").click()

    _fill_number(page, "Loan Amount (PLN)", "30000")
    _fill_number(page, "Annual Interest Rate (%)", "9.5")
    _fill_number(page, "Term (months)", "36")

    page.get_by_role("button", name="Calculate").click()

    expect(page.get_by_text("Monthly Payment", exact=True)).to_be_visible(timeout=5000)
    expect(page.get_by_text("Total Interest", exact=True)).to_be_visible(timeout=5000)
    expect(page.get_by_text("Total Cost", exact=True)).to_be_visible(timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: Calculate a car loan with equal installments + amortization table
# ---------------------------------------------------------------------------

def test_calculate_car_loan_equal_installments_with_schedule(page: Page) -> None:
    """Scenario: Calculate a car loan with equal installments"""
    page.goto(f"{BASE_URL}/credit-calculator")

    page.locator(".q-select").filter(has_text="Payment Type").click()
    page.get_by_role("option", name="Equal installments (annuity)").click()

    _fill_number(page, "Loan Amount (PLN)", "80000")
    _fill_number(page, "Annual Interest Rate (%)", "7.99")
    _fill_number(page, "Term (months)", "60")

    page.get_by_role("button", name="Calculate").click()

    expect(page.get_by_text("Monthly Payment", exact=True)).to_be_visible(timeout=5000)
    expect(page.get_by_text("Total Interest", exact=True)).to_be_visible(timeout=5000)
    expect(page.get_by_text("Payment Schedule")).to_be_visible(timeout=5000)
    expect(page.locator(".q-table")).to_be_visible(timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: Calculate a mortgage with equal installments
# ---------------------------------------------------------------------------

def test_calculate_mortgage_equal_installments(page: Page) -> None:
    """Scenario: Calculate a mortgage with equal installments"""
    page.goto(f"{BASE_URL}/credit-calculator")

    page.locator(".q-select").filter(has_text="Payment Type").click()
    page.get_by_role("option", name="Equal installments (annuity)").click()

    _fill_number(page, "Loan Amount (PLN)", "500000")
    _fill_number(page, "Annual Interest Rate (%)", "6.5")
    _fill_number(page, "Term (months)", "360")

    page.get_by_role("button", name="Calculate").click()

    expect(page.get_by_text("Monthly Payment", exact=True)).to_be_visible(timeout=5000)
    expect(page.get_by_text("Total Interest", exact=True)).to_be_visible(timeout=5000)
    expect(page.get_by_text("Payment Schedule")).to_be_visible(timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: Compare equal vs decreasing installments
# ---------------------------------------------------------------------------

def test_compare_equal_vs_decreasing_installments(page: Page) -> None:
    """Scenario: Compare equal vs decreasing installments"""
    page.goto(f"{BASE_URL}/credit-calculator")

    _fill_number(page, "Loan Amount (PLN)", "100000")
    _fill_number(page, "Annual Interest Rate (%)", "8.0")
    _fill_number(page, "Term (months)", "120")

    # Equal installments first
    page.locator(".q-select").filter(has_text="Payment Type").click()
    page.get_by_role("option", name="Equal installments (annuity)").click()

    page.get_by_role("button", name="Calculate").click()

    expect(page.get_by_text("Monthly Payment", exact=True)).to_be_visible(timeout=5000)
    expect(page.get_by_text("Total Interest", exact=True)).to_be_visible(timeout=5000)

    # Switch to decreasing installments
    page.locator(".q-select").filter(has_text="Payment Type").click()
    page.get_by_role("option", name="Decreasing installments").click()

    page.get_by_role("button", name="Calculate").click()

    # Decreasing shows first/last payment range instead of single monthly payment
    expect(page.get_by_text("First → Last Payment")).to_be_visible(timeout=5000)
    expect(page.get_by_text("Total Interest", exact=True)).to_be_visible(timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: Simulate overpayment to shorten loan term
# ---------------------------------------------------------------------------

def test_simulate_overpayment_shortens_loan_term(page: Page) -> None:
    """Scenario: Simulate overpayment to shorten loan term"""
    page.goto(f"{BASE_URL}/credit-calculator")

    page.locator(".q-select").filter(has_text="Payment Type").click()
    page.get_by_role("option", name="Equal installments (annuity)").click()

    _fill_number(page, "Loan Amount (PLN)", "500000")
    _fill_number(page, "Annual Interest Rate (%)", "6.5")
    _fill_number(page, "Term (months)", "360")
    _fill_number(page, "Extra Monthly Payment (PLN)", "500")

    page.get_by_role("button", name="Calculate").click()

    expect(page.get_by_text("Overpayment Savings")).to_be_visible(timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: Page loads with defaults and produces valid results
# ---------------------------------------------------------------------------

def test_page_shows_results_with_valid_defaults(page: Page) -> None:
    """Page loads with pre-filled defaults and can calculate without error."""
    page.goto(f"{BASE_URL}/credit-calculator")

    # Default values: 300k PLN, 7.5%, 360 months
    page.get_by_role("button", name="Calculate").click()

    expect(page.get_by_text("Monthly Payment", exact=True)).to_be_visible(timeout=5000)
    expect(page.get_by_text("Total Interest", exact=True)).to_be_visible(timeout=5000)
    expect(page.get_by_text("Total Cost", exact=True)).to_be_visible(timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: Zero interest rate shows validation message
# ---------------------------------------------------------------------------

def test_zero_rate_shows_valid_params_message(page: Page) -> None:
    """Scenario: Interest rate must be positive — zero triggers error hint."""
    page.goto(f"{BASE_URL}/credit-calculator")

    # NiceGUI number field enforces min=0.01 so we must set it to 0 via JS or
    # verify the guard message. Fill in valid amount and term, only zero the rate.
    _fill_number(page, "Loan Amount (PLN)", "100000")
    _fill_number(page, "Annual Interest Rate (%)", "0.00")
    _fill_number(page, "Term (months)", "24")

    page.get_by_role("button", name="Calculate").click()

    # When rate <= 0 the view shows this message instead of results
    expect(page.get_by_text("Enter valid loan parameters.")).to_be_visible(timeout=5000)
