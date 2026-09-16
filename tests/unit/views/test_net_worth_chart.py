# SPDX-License-Identifier: AGPL-3.0-or-later
"""The net-worth chart's options and the headline figure (artboard 3b).

The stacking in this chart is deliberate — the top edge is assets *plus*
liabilities, not net worth — so what the chart says about itself is the thing
worth testing. Presentational; no BDD scenario claims it.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from kaleta.schemas.account import AccountType
from kaleta.services.net_worth_service import AccountSnapshot, MonthlyNetWorth, NetWorthSummary
from kaleta.views.net_worth import net_worth_chart_options, split_figure


def _summary() -> NetWorthSummary:
    accounts = [
        AccountSnapshot(
            id=1,
            name="Checking",
            type=AccountType.CHECKING,
            institution_name=None,
            balance=Decimal("6000.00"),
            balance_in_default=Decimal("6000.00"),
        )
    ]
    history = [
        MonthlyNetWorth(
            year=2025,
            month=m,
            net_worth=Decimal("1000.00"),
            total_assets=Decimal("8000.00"),
            total_liabilities=Decimal("2000.00"),
        )
        for m in (1, 2)
    ]
    return NetWorthSummary(
        accounts=accounts, physical_assets=[], history=history, prev_month_net_worth=None
    )


class TestChartOptions:
    def test_the_legend_says_the_liabilities_are_stacked_on_the_assets(self) -> None:
        # Without this the upper line reads as a total the user never has.
        options = net_worth_chart_options(_summary(), dark=False)
        names = [s["name"] for s in options["series"]]
        assert options["legend"]["data"] == names
        assert "stacked" in names[1].lower()

    def test_both_series_share_one_stack(self) -> None:
        options = net_worth_chart_options(_summary(), dark=False)
        stacks = {s["stack"] for s in options["series"]}
        assert len(stacks) == 1

    def test_the_axis_starts_at_zero(self) -> None:
        # A floating baseline makes a steady balance sheet look like a cliff.
        assert net_worth_chart_options(_summary(), dark=False)["yAxis"]["min"] == 0

    def test_each_line_says_where_it_ends(self) -> None:
        options = net_worth_chart_options(_summary(), dark=False)
        assert all(s["endLabel"]["show"] for s in options["series"])

    def test_the_fills_stay_light_enough_to_read_the_lower_band_through(self) -> None:
        options = net_worth_chart_options(_summary(), dark=False)
        assert all(s["areaStyle"]["opacity"] <= 0.25 for s in options["series"])

    def test_the_series_carry_the_history_in_thousands(self) -> None:
        options = net_worth_chart_options(_summary(), dark=False)
        assert options["series"][0]["data"] == [8.0, 8.0]
        assert options["series"][1]["data"] == [2.0, 2.0]

    def test_dark_mode_changes_the_axis_and_not_the_stacking(self) -> None:
        light = net_worth_chart_options(_summary(), dark=False)
        dark = net_worth_chart_options(_summary(), dark=True)
        assert [s["data"] for s in light["series"]] == [s["data"] for s in dark["series"]]
        assert light["xAxis"] != dark["xAxis"]


class TestSplitFigure:
    @pytest.mark.parametrize(
        ("amount", "expected"),
        [
            (Decimal("1234567.89"), ("1,234,567", ".89 PLN")),
            (Decimal("0.00"), ("0", ".00 PLN")),
            (Decimal("-1500.50"), ("-1,500", ".50 PLN")),
        ],
    )
    def test_the_grosze_split_off_without_the_halves_disagreeing(
        self, amount: Decimal, expected: tuple[str, str]
    ) -> None:
        assert split_figure(amount) == expected

    def test_the_currency_rides_with_the_decimals(self) -> None:
        assert split_figure(Decimal("12.30"), "EUR") == ("12", ".30 EUR")
