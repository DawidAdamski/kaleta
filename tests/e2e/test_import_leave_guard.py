# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E: leaving /import with an unfinished queue asks first.

Covers: KAL-CSV-042

The queue lives only in the page's memory, so any full navigation away drops
it. While a file still waits to be imported, the page arms the browser's own
"leave this page?" prompt; a sidebar link is a full page load, so it raises
that prompt too. Once every file has finished, the prompt is gone.
Page URL: /import
"""

from __future__ import annotations

import re
import uuid

from playwright.sync_api import Dialog, FilePayload, Page, expect

from tests.e2e.ledger import pick_open_menu_option
from tests.e2e.pages import on_import_page
from tests.e2e.seed_helpers import seed_account, seed_category, seed_income_category

GUARD = "typeof window.__kaletaImportLeaveGuard"


def _statement(name: str) -> FilePayload:
    """A generic CSV whose rows no other run has imported, so none is a duplicate."""
    tag = uuid.uuid4().hex[:8]
    body = f"date,amount,description\n2024-02-03,-12.34,Leave guard {tag}\n"
    return FilePayload(name=name, mimeType="text/csv", buffer=body.encode())


def _step(page: Page, step: int) -> None:
    page.keyboard.press("Escape")
    node = page.locator(f'[data-step="{step}"]')
    expect(node).to_have_class(re.compile(r"cursor-pointer"), timeout=5000)
    node.click()
    expect(page.locator(f'[data-step-panel="{step}"]')).to_be_visible(timeout=5000)


def _pick(page: Page, label: str, option: str) -> None:
    page.keyboard.press("Escape")
    page.locator(".q-select").filter(has_text=label).click()
    pick_open_menu_option(page, option)


def _sidebar_dashboard(page: Page) -> None:
    """The pinned sidebar entry: always visible, a full page load like every nav item."""
    page.locator(".q-drawer .q-item").filter(has_text="Dashboard").first.click()


def test_leave_guard_active_with_queued_file(page: Page, base_url: str) -> None:
    """Covers: KAL-CSV-042

    With two files queued, the guard is armed; a sidebar click raises the
    browser's prompt, and cancelling it keeps the page and both files.
    """
    page.goto(f"{base_url}/import")
    on_import_page(page)
    page.locator('input[type="file"]').set_input_files(
        [_statement("leave-guard-a.csv"), _statement("leave-guard-b.csv")]
    )
    expect(page.locator("[data-queue-row]")).to_have_count(2, timeout=10000)
    assert page.evaluate(GUARD) == "function"

    prompts: list[str] = []

    def _cancel(dialog: Dialog) -> None:
        prompts.append(dialog.type)
        dialog.dismiss()

    page.on("dialog", _cancel)
    _sidebar_dashboard(page)
    for _ in range(50):
        if prompts:
            break
        page.wait_for_timeout(100)
    assert prompts == ["beforeunload"]

    page.wait_for_timeout(1000)
    assert page.url.rstrip("/").endswith("/import")
    on_import_page(page)
    expect(page.locator("[data-queue-row]")).to_have_count(2)


def test_leave_guard_cleared_after_import(page: Page, base_url: str) -> None:
    """Covers: KAL-CSV-042

    After the only queued file is imported, nothing is left to lose: the guard
    is gone and a sidebar click leaves without a prompt.
    """
    account = "Leave Guard E2E Account"
    expense = "Leave Guard E2E Expenses"
    income = "Leave Guard E2E Income"
    seed_account(account)
    seed_category(expense)
    seed_income_category(income)

    page.goto(f"{base_url}/import")
    on_import_page(page)
    page.locator('input[type="file"]').set_input_files(_statement("leave-guard-run.csv"))
    expect(page.locator("[data-page-eyebrow]")).to_contain_text(
        "leave-guard-run.csv", timeout=10000
    )
    assert page.evaluate(GUARD) == "function"

    _step(page, 4)
    _pick(page, "Target account", f"{account} (PLN)")
    _pick(page, "Default expense category", expense)
    _pick(page, "Default income category", income)
    _step(page, 5)
    run = page.locator("[data-import-run]")
    expect(run).to_be_enabled(timeout=5000)
    run.click()
    expect(page.locator('[data-step-panel="6"]')).to_contain_text(
        re.compile(r"\b1 imported"), timeout=10000
    )

    page.wait_for_function(f"{GUARD} === 'undefined'", timeout=5000)
    prompts: list[str] = []
    page.on("dialog", lambda dialog: (prompts.append(dialog.type), dialog.dismiss()))
    _sidebar_dashboard(page)
    page.wait_for_url(lambda url: "/import" not in url, timeout=10000)
    assert prompts == []
