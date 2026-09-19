# SPDX-License-Identifier: AGPL-3.0-or-later
"""Helpers for driving the transactions ledger from e2e tests.

The filters became chips (artboard 2a): each control now lives in a menu that
opens from its chip and overlays the table, so a test that wants to type into
one has to open it first and close it before touching the rows underneath.
"""

from __future__ import annotations

from playwright.sync_api import Page, expect


def search_ledger(page: Page, text: str) -> None:
    """Filter the ledger by description through the search chip."""
    chip = page.locator(".k-chip-search")
    expect(chip).to_be_visible(timeout=10000)
    chip.click()
    # Exact: each chip's clear icon is labelled "Clear <field>", which a
    # substring match would also pick up.
    search = page.get_by_label("Search description", exact=True)
    expect(search).to_be_visible(timeout=5000)
    search.click(click_count=3)
    search.fill(text)
    page.keyboard.press("Escape")


def pick_open_menu_option(page: Page, option: str) -> None:
    """Pick an option from the open Quasar menu, scrolling virtual lists if needed.

    A select the suite has filled with dozens of rows renders only the slice
    in view, so an option that exists is not necessarily in the DOM yet.
    """
    menu = page.locator(".q-menu").last
    expect(menu).to_be_visible(timeout=3000)
    target = menu.get_by_text(option, exact=True)
    for _ in range(40):
        if target.count() > 0:
            target.first.click()
            return
        menu.evaluate(
            """(el) => {
              const scroller =
                el.querySelector('.q-virtual-scroll__content')?.parentElement
                || el.querySelector('.scroll')
                || el;
              scroller.scrollTop += 220;
            }"""
        )
        page.wait_for_timeout(40)
    raise AssertionError(f"Select option not found after scrolling: {option!r}")


def filter_ledger_by_account(page: Page, account_name: str) -> None:
    """Narrow the ledger to one account through the accounts chip."""
    chip = page.locator(".k-chip-accounts")
    expect(chip).to_be_visible(timeout=10000)
    chip.click()
    page.locator(".q-menu").last.locator(".q-select").click()
    pick_open_menu_option(page, account_name)
    page.keyboard.press("Escape")
    page.keyboard.press("Escape")
