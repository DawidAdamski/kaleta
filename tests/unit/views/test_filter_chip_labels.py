# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for the transactions ledger chrome (artboard 2a).

A chip has to say what is filtered, in the words of artboard 2a:
``01.06.2026 → 03.07.2026``, ``PKO Konto Główne +2``, ``Expense``. Every
expected string below is quoted from that artboard.
"""

from __future__ import annotations

import datetime
from typing import Any

from kaleta.schemas.transaction import TransactionType
from kaleta.views.components.filter_bar import (
    active_filter_count,
    filter_chip_label,
    format_date_range,
    summarise_selection,
)

ACCOUNTS = {1: "PKO Konto Główne", 2: "mBank Oszczędności", 3: "Revolut"}
CATEGORIES = {10: "Żywność", 11: "Subskrypcje"}
TYPES = {"income": "Income", "expense": "Expense", "transfer": "Transfer"}
TAGS = {20: "codzienne", 21: "abonament"}


def _label(field_name: str, **filters: Any) -> tuple[str, str]:
    return filter_chip_label(
        field_name,
        filters,
        account_options=ACCOUNTS,
        category_options=CATEGORIES,
        type_options=TYPES,
        tag_options=TAGS,
    )


class TestDateRange:
    def test_both_ends_read_as_the_artboard_does(self) -> None:
        assert (
            format_date_range(datetime.date(2026, 6, 1), datetime.date(2026, 7, 3))
            == "01.06.2026 → 03.07.2026"
        )

    def test_only_a_start_keeps_the_arrow(self) -> None:
        assert format_date_range(datetime.date(2026, 6, 1), None) == "01.06.2026 →"

    def test_only_an_end_keeps_the_arrow(self) -> None:
        assert format_date_range(None, datetime.date(2026, 7, 3)) == "→ 03.07.2026"

    def test_neither_end_is_an_empty_chip(self) -> None:
        assert format_date_range(None, None) == ""


class TestSelectionSummary:
    def test_one_name_has_no_tail(self) -> None:
        assert summarise_selection(["PKO Konto Główne"]) == ("PKO Konto Główne", "")

    def test_three_names_show_the_first_and_a_count(self) -> None:
        assert summarise_selection(["PKO Konto Główne", "mBank Oszczędności", "Revolut"]) == (
            "PKO Konto Główne",
            "+2",
        )

    def test_nothing_selected_is_an_empty_chip(self) -> None:
        assert summarise_selection([]) == ("", "")


class TestChipLabels:
    def test_accounts_chip_matches_the_artboard(self) -> None:
        assert _label("accounts", account_ids=[1, 2, 3]) == ("PKO Konto Główne", "+2")

    def test_type_chip_reads_the_label_not_the_enum(self) -> None:
        assert _label("types", tx_types=[TransactionType.EXPENSE]) == ("Expense", "")

    def test_type_chip_accepts_plain_strings_too(self) -> None:
        # The page stores enums; a cleared filter stores nothing at all.
        assert _label("types", tx_types=["expense"]) == ("Expense", "")

    def test_category_chip(self) -> None:
        assert _label("categories", category_ids=[10, 11]) == ("Żywność", "+1")

    def test_tag_chip(self) -> None:
        assert _label("tags", tag_ids=[20]) == ("codzienne", "")

    def test_search_chip_carries_the_text(self) -> None:
        main, extra = _label("search", search="Lidl")
        assert "Lidl" in main
        assert extra == ""

    def test_whitespace_is_not_a_search(self) -> None:
        assert _label("search", search="   ") == ("", "")

    def test_an_id_that_no_longer_exists_is_skipped(self) -> None:
        # A saved filter can outlive the account it names.
        assert _label("accounts", account_ids=[99]) == ("", "")

    def test_every_chip_is_empty_for_empty_filters(self) -> None:
        for field_name in ("date", "accounts", "categories", "types", "tags", "search"):
            assert _label(field_name) == ("", ""), field_name


class TestActiveFilterCount:
    def test_counts_the_three_the_artboard_shows(self) -> None:
        filters = {
            "date_from": datetime.date(2026, 6, 1),
            "account_ids": [1, 2, 3],
            "tx_types": [TransactionType.EXPENSE],
        }

        # date_from, accounts, types — "Clear all 3".
        assert active_filter_count(filters) == 3
