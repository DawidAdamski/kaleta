# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Bug reports.

Covers: KAL-BUG-001, KAL-BUG-002, KAL-BUG-004

Page URL: /settings (Privacy & diagnostics tab)
"""

from __future__ import annotations

import re
from typing import Any

from playwright.sync_api import Page, expect

from tests.e2e.seed_helpers import _run_async_worker

REPORT_ID_RE = re.compile(r"Report ID: ([0-9A-Z]{8})")


def _read_report(report_id: str) -> dict[str, Any]:
    """Read one report straight from the e2e database."""

    async def _query() -> dict[str, Any]:
        from kaleta.db import AsyncSessionFactory
        from kaleta.services.bug_report_service import BugReportService

        async with AsyncSessionFactory() as session:
            report = await BugReportService(session).get(report_id)
            return {
                "summary": report.summary,
                "description": report.description,
                "event_ids": list(report.event_ids or []),
                "log_excerpt": report.log_excerpt,
                "route": report.route,
                "status": str(report.status),
            }

    return _run_async_worker(_query)


def _open_privacy_tab(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/settings")
    page.get_by_role("tab", name="Privacy & diagnostics").click()
    expect(page.get_by_text("Diagnostics", exact=True)).to_be_visible(timeout=10000)


def _file_report(page: Page, summary: str, description: str) -> str:
    """Trigger a failure, report it from the tray, and return the report id."""
    page.get_by_role("button", name="Trigger a test error").click()

    tray = page.locator(".k-error-tray")
    expect(tray).to_be_visible(timeout=10000)
    expect(tray.get_by_text(re.compile(r"Event ID: [0-9A-Z]{8}"))).to_be_visible(timeout=10000)
    tray.get_by_role("button", name="Report", exact=True).click()

    dialog = page.get_by_role("dialog")
    expect(dialog.get_by_text("Report a problem", exact=True)).to_be_visible(timeout=10000)
    # The box that would attach log lines starts unticked — KAL-BUG-002.
    expect(dialog.get_by_role("checkbox")).not_to_be_checked()

    dialog.get_by_label("Summary", exact=True).fill(summary)
    dialog.get_by_label("What were you doing?", exact=True).fill(description)
    dialog.get_by_role("button", name="Send report").click()

    expect(dialog.get_by_text("Report sent", exact=True)).to_be_visible(timeout=10000)
    shown = dialog.get_by_text(REPORT_ID_RE).inner_text()
    match = REPORT_ID_RE.search(shown)
    assert match, f"no report id in {shown!r}"
    dialog.get_by_role("button", name="Close").click()
    return match.group(1)


def test_reporting_a_problem_from_the_error_tray(page: Page, base_url: str) -> None:
    """Covers: KAL-BUG-001, KAL-BUG-002

    The tray that follows a failure carries the event id into the report, and
    the log excerpt stays behind unless the user ticks the box.
    """
    _open_privacy_tab(page, base_url)
    report_id = _file_report(
        page,
        "Test error while checking diagnostics",
        "I pressed the test-error button in Settings.",
    )

    stored = _read_report(report_id)
    assert stored["summary"] == "Test error while checking diagnostics"
    assert stored["description"] == "I pressed the test-error button in Settings."
    assert len(stored["event_ids"]) == 1
    assert re.fullmatch(r"[0-9A-Z]{8}", stored["event_ids"][0])
    assert stored["log_excerpt"] is None
    assert stored["route"] == "/settings"
    assert stored["status"] == "new"


def test_a_user_can_withdraw_a_report(page: Page, base_url: str) -> None:
    """Covers: KAL-BUG-004

    A report the user filed is listed back to them, and deleting it withdraws
    it from the maintainer's queue.
    """
    _open_privacy_tab(page, base_url)
    report_id = _file_report(page, "Report to withdraw", "Filed, then taken back.")

    page.reload()
    page.get_by_role("tab", name="Privacy & diagnostics").click()
    row_id = page.get_by_text(report_id, exact=True)
    expect(row_id).to_be_visible(timeout=10000)

    page.get_by_role("button", name="Delete this report").first.click()
    expect(page.get_by_text("Report deleted", exact=True)).to_be_visible(timeout=10000)
    expect(page.get_by_text(report_id, exact=True)).to_have_count(0, timeout=10000)
