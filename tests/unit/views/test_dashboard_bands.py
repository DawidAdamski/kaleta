# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for the phone dashboard's band grouping and hero bar (1f)."""

from __future__ import annotations

import datetime
from dataclasses import replace
from decimal import Decimal

from kaleta.services.report_service import SafeToSpend
from kaleta.views.dashboard_widgets import (
    DEFAULT_WIDGETS,
    Band,
    bands_for_layout,
    mobile_layout,
)
from kaleta.views.dashboard_widgets.registry import HERO_WIDGET, LEGACY_KPI_WIDGETS, WIDGETS
from kaleta.views.dashboard_widgets.safe_to_spend import days_left_label, hero_split


def _entry(widget_id: str) -> dict[str, object]:
    widget = WIDGETS[widget_id]
    return {"id": widget_id, "cols": widget.default_size[0], "rows": widget.default_size[1]}


def _ids(entries: list[dict[str, object]]) -> list[object]:
    return [entry["id"] for entry in entries]


class TestBandsForLayout:
    def test_an_unlisted_widget_falls_into_the_month_band(self) -> None:
        """The safe default: most of the catalog is about this month."""
        grouped = bands_for_layout([_entry("cashflow_chart")])

        assert _ids(grouped[Band.MONTH]) == ["cashflow_chart"]
        assert grouped[Band.NOW] == []

    def test_order_inside_a_band_follows_the_stored_layout(self) -> None:
        layout = [_entry("quick_actions"), _entry("wizard_actions")]

        grouped = bands_for_layout(layout)

        assert _ids(grouped[Band.NOW]) == ["quick_actions", "wizard_actions"]

    def test_legacy_widgets_are_dropped_rather_than_banded(self) -> None:
        """They are the seven the merged cards replaced; the phone never had them."""
        layout = [_entry(wid) for wid in LEGACY_KPI_WIDGETS]

        grouped = bands_for_layout(layout)

        assert all(entries == [] for entries in grouped.values())

    def test_an_unknown_id_is_ignored(self) -> None:
        """A stored layout outlives the widget it names."""
        grouped = bands_for_layout([{"id": "widget_that_left", "cols": 1, "rows": 1}])

        assert all(entries == [] for entries in grouped.values())


class TestMobileLayout:
    def test_the_hero_leads_a_layout_that_does_not_carry_it(self) -> None:
        """It is off by default on the desktop grid, so a phone must add it."""
        result = mobile_layout([_entry("cashflow_chart")])

        assert _ids(result) == [HERO_WIDGET, "cashflow_chart"]

    def test_a_layout_that_already_has_it_is_left_alone(self) -> None:
        """Twice on one screen is worse than once in the wrong place."""
        layout = [_entry("cashflow_chart"), _entry(HERO_WIDGET)]

        result = mobile_layout(layout)

        assert _ids(result) == ["cashflow_chart", HERO_WIDGET]

    def test_the_hero_lands_in_the_now_band(self) -> None:
        grouped = bands_for_layout(mobile_layout([_entry("cashflow_chart")]))

        assert _ids(grouped[Band.NOW]) == [HERO_WIDGET]


class TestWatchBandTakesNoWidgets:
    def test_no_widget_is_assigned_to_watch(self) -> None:
        """The band is four figures in plain type; a card under them would
        repeat what they already say."""
        grouped = bands_for_layout([_entry(wid) for wid in DEFAULT_WIDGETS])

        assert grouped[Band.WATCH] == []


#: A zero month on the 10th of a 30-day one; every test states only what it
#: changes. ``replace`` keeps the builder typed, which a dict spread could not.
_BLANK = SafeToSpend(
    today=datetime.date(2026, 6, 10),
    income=Decimal("0.00"),
    committed=Decimal("0.00"),
    spent=Decimal("0.00"),
    trailing_avg_per_day=Decimal("0.00"),
)


def _stats(**kwargs: Decimal | datetime.date) -> SafeToSpend:
    return replace(_BLANK, **kwargs)


class TestHeroSplit:
    def test_three_shares_add_up_to_the_whole_bar(self) -> None:
        split = hero_split(
            _stats(
                income=Decimal("1000.00"),
                committed=Decimal("250.00"),
                spent=Decimal("250.00"),
            )
        )

        assert split is not None
        assert round(split.committed + split.spent + split.free, 6) == 100.0
        assert round(split.free, 4) == 50.0

    def test_an_empty_month_has_no_bar(self) -> None:
        """Nothing in, nothing out: three zero-width segments, so no track."""
        assert hero_split(_stats()) is None

    def test_an_overspent_month_shows_no_free_segment(self) -> None:
        """A negative width would push the other two off the end of the track."""
        split = hero_split(_stats(income=Decimal("100.00"), spent=Decimal("400.00")))

        assert split is not None
        assert split.free == 0.0
        assert round(split.spent, 4) == 100.0


class TestDaysLeftLabel:
    def test_one_day_reads_singular(self) -> None:
        assert days_left_label(_stats(today=datetime.date(2026, 6, 30))) == (
            "1 day left this month"
        )

    def test_more_than_one_reads_plural(self) -> None:
        assert days_left_label(_stats()) == "21 days left this month"


class TestOverspentMonth:
    """`spendable` is what the hero reads to decide which line to print."""

    def test_a_month_with_nothing_left_is_not_spendable(self) -> None:
        stats = _stats(income=Decimal("1000.00"), spent=Decimal("1300.00"))

        assert stats.spendable is False
        assert stats.free == Decimal("-300.00")

    def test_a_month_with_something_left_is(self) -> None:
        assert _stats(income=Decimal("1000.00")).spendable is True

    def test_an_empty_month_is_spendable_at_zero(self) -> None:
        """An empty ledger, or the 1st before anything has posted.

        `0.00 zł over`, in red, is the wrong thing to tell somebody who has
        not spent anything — and it is what the whole app says on first run.
        """
        stats = _stats()

        assert stats.free == Decimal("0.00")
        assert stats.spendable is True

    def test_a_month_exactly_at_its_limit_is_spendable(self) -> None:
        assert _stats(income=Decimal("500.00"), spent=Decimal("500.00")).spendable is True

    def test_one_grosz_past_the_limit_is_not(self) -> None:
        assert _stats(income=Decimal("500.00"), spent=Decimal("500.01")).spendable is False
