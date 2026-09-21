# SPDX-License-Identifier: AGPL-3.0-or-later
"""The report query read back as words (artboard 3e).

The sentence is the builder's only statement of what it is about to ask, so
what each slot says has to follow the state exactly. Presentational; no BDD
scenario claims these directly — KAL-RPT-001 exercises them through the page.
"""

from __future__ import annotations

from typing import Any

from kaleta.views.reports.constants import BUILDER_STATE_DEFAULTS
from kaleta.views.reports.sentence import (
    period_label,
    result_total,
    share_percents,
    slot_labels,
    top_n_label,
    types_label,
)


def _state(**overrides: Any) -> dict[str, Any]:
    state = dict(BUILDER_STATE_DEFAULTS)
    state.update(overrides)
    return state


class TestSlotLabels:
    def test_the_defaults_read_as_the_page_opens(self) -> None:
        slots = slot_labels(_state())
        assert slots.metric == "Total Amount"
        assert slots.dimension == "Category"
        assert slots.types == "Expense"
        assert slots.period == "This Year"
        assert slots.top_n == "10"

    def test_a_slot_follows_its_state(self) -> None:
        slots = slot_labels(_state(dimension="account", metric="count"))
        assert slots.dimension == "Account"
        assert slots.metric == "Count"

    def test_an_unknown_key_reads_as_nothing_rather_than_crashing(self) -> None:
        # State can come from a saved report written by an older version.
        assert slot_labels(_state(dimension="planet")).dimension == "—"


class TestTypesLabel:
    def test_one_type_is_named(self) -> None:
        assert types_label(_state(transaction_types=["income"])) == "Income"

    def test_two_are_joined(self) -> None:
        label = types_label(_state(transaction_types=["expense", "income"]))
        assert label == "Expense + Income"

    def test_the_join_follows_the_table_order_not_the_click_order(self) -> None:
        # Otherwise the same filter reads differently depending on which box
        # the user happened to tick first.
        clicked = _state(transaction_types=["income", "expense"])
        assert types_label(clicked) == "Expense + Income"

    def test_excluding_nothing_is_not_a_filter(self) -> None:
        every = _state(transaction_types=["expense", "income", "transfer"])
        assert types_label(every) == "all types"

    def test_no_types_at_all_reads_as_nothing(self) -> None:
        assert types_label(_state(transaction_types=[])) == "—"


class TestPeriodLabel:
    def test_a_preset_is_named_not_resolved(self) -> None:
        # The engine owns the arithmetic that turns "this year" into dates;
        # restating it here would be a second copy of it to keep in step.
        assert period_label(_state(date_preset="last_month")) == "Last Month"

    def test_a_custom_range_shows_both_of_its_dates(self) -> None:
        state = _state(date_preset="custom", date_from="2026-01-01", date_to="2026-03-31")
        assert period_label(state) == "2026-01-01 – 2026-03-31"

    def test_a_half_finished_custom_range_says_which_half_it_has(self) -> None:
        assert period_label(_state(date_preset="custom", date_from="2026-01-01")) == (
            "from 2026-01-01"
        )
        assert period_label(_state(date_preset="custom", date_to="2026-03-31")) == (
            "until 2026-03-31"
        )

    def test_an_empty_custom_range_falls_back_to_its_own_name(self) -> None:
        assert period_label(_state(date_preset="custom")) == "Custom Range"


class TestTopNLabel:
    def test_a_limit_is_its_number(self) -> None:
        assert top_n_label(_state(top_n=25)) == "25"

    def test_zero_is_no_limit_not_nothing(self) -> None:
        # `report_config_from_builder_state` turns 0 into None, which means
        # "every row" — so "top 0" would say the exact opposite.
        assert top_n_label(_state(top_n=0)) == "no limit"


class TestResultTotal:
    """The figure on the result card's title line (artboard 3e)."""

    def test_it_adds_the_rows_up_and_spaces_the_thousands(self) -> None:
        assert result_total([24279.31, 5522.40, 5091.53], metric="sum") == "34 893.24"

    def test_a_negative_row_is_subtracted_rather_than_counted(self) -> None:
        # Unlike a share, a total keeps its signs: a net dimension that comes
        # to nothing has to say nothing, not say twice its largest row.
        assert result_total([900.0, -900.0], metric="sum") == "0.00"

    def test_no_rows_at_all(self) -> None:
        assert result_total([], metric="sum") == "0.00"

    def test_counts_add_up_to_something_a_reader_can_use(self) -> None:
        """Covers: KAL-RPT-004"""
        assert result_total([12.0, 8.0], metric="count") == "20.00"

    def test_averages_do_not_add_up_at_all(self) -> None:
        """Covers: KAL-RPT-004"""
        # Twelve monthly averages summed is not the average of anything, and
        # the card draws no total rather than a figure captioned "total".
        assert result_total([300.0, 420.0], metric="avg") is None


class TestSharePercents:
    def test_shares_add_up_to_a_hundred(self) -> None:
        shares = share_percents([25.0, 25.0, 50.0])
        assert shares == [25.0, 25.0, 50.0]
        assert sum(shares) == 100.0

    def test_a_negative_value_takes_its_size_not_its_sign(self) -> None:
        # An expense report's values are positive, but a net dimension can
        # produce both — and a bar's share of the whole is about magnitude.
        assert share_percents([-30.0, 70.0]) == [30.0, 70.0]

    def test_a_total_of_nothing_has_no_shares_to_give(self) -> None:
        assert share_percents([0.0, 0.0]) == [0.0, 0.0]

    def test_no_values_at_all(self) -> None:
        assert share_percents([]) == []
