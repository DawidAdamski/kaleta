"""E2E tests for Feature: Single-user authentication.

Covers: KAL-AUTH-001, KAL-AUTH-002, KAL-AUTH-003, KAL-AUTH-004, KAL-AUTH-005, KAL-AUTH-006
"""

from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from tests.e2e.conftest import E2E_PASSWORD, E2E_USERNAME


def test_login_success(page_no_auth: Page, base_url: str) -> None:
    """Covers: KAL-AUTH-001"""
    page_no_auth.goto(f"{base_url}/login")
    page_no_auth.get_by_label("Username", exact=True).fill(E2E_USERNAME)
    page_no_auth.get_by_label("Password", exact=True).fill(E2E_PASSWORD)
    page_no_auth.get_by_role("button", name="Log in").click()

    expect(page_no_auth).not_to_have_url(f"{base_url}/login", timeout=10000)
    page_no_auth.goto(f"{base_url}/")
    expect(page_no_auth.get_by_text("Dashboard", exact=True).first).to_be_visible(timeout=10000)


def test_login_wrong_password(page_no_auth: Page, base_url: str) -> None:
    """Covers: KAL-AUTH-002"""
    page_no_auth.goto(f"{base_url}/login")
    page_no_auth.get_by_label("Username", exact=True).fill(E2E_USERNAME)
    page_no_auth.get_by_label("Password", exact=True).fill("definitely-wrong")
    page_no_auth.get_by_role("button", name="Log in").click()

    expect(page_no_auth).to_have_url(f"{base_url}/login", timeout=5000)
    expect(page_no_auth.get_by_text("Invalid username or password.")).to_be_visible(timeout=5000)


def test_guard_redirects_unauthenticated_deep_link(page_no_auth: Page, base_url: str) -> None:
    """Covers: KAL-AUTH-003"""
    page_no_auth.goto(f"{base_url}/transactions")

    expect(page_no_auth).to_have_url(f"{base_url}/login?redirect_to=/transactions", timeout=10000)


def test_guard_redirects_unauthenticated_setup(page_no_auth: Page, base_url: str) -> None:
    """Covers: KAL-AUTH-004"""
    page_no_auth.goto(f"{base_url}/setup")

    expect(page_no_auth).to_have_url(f"{base_url}/login?redirect_to=/setup", timeout=10000)


def test_api_unauthorized_without_token(base_url: str) -> None:
    """Covers: KAL-AUTH-005"""
    resp = httpx.get(f"{base_url}/api/v1/accounts/", timeout=10.0)
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


def test_api_authorized_with_bearer_token(base_url: str, e2e_api_token: str) -> None:
    """Covers: KAL-AUTH-006"""
    resp = httpx.get(
        f"{base_url}/api/v1/accounts/",
        headers={"Authorization": f"Bearer {e2e_api_token}"},
        timeout=10.0,
    )
    assert resp.status_code == 200
