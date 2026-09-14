# SPDX-License-Identifier: AGPL-3.0-or-later
"""The forecast chart's options, and the page's staleness rule (artboard 3a).

Covers: KAL-FCT-001 — "a shaded confidence interval surrounds the prediction".
Surrounds is the word the old chart got wrong: it stacked the band's height
on top of the *upper* bound, so the shading sat entirely above the line it
was meant to contain.
"""

from __future__ import annotations

import datetime
from typing import Any

from kaleta.services.forecast_service import ForecastPoint, ForecastResult, ScenarioShift
from kaleta.views.forecast import _forecast_chart, stale_action

TODAY = datetime.date.today()


def _point(offset: int, value: float, *, lower: float, upper: float, forecast: bool):
    return ForecastPoint(
        date=TODAY + datetime.timedelta(days=offset),
        value=value,
        lower=lower,
        upper=upper,
        is_forecast=forecast,
    )


def _result() -> ForecastResult:
    return ForecastResult(
        account_name="PKO",
        points=[
            _point(-2, 1000.0, lower=1000.0, upper=1000.0, forecast=False),
            _point(-1, 1010.0, lower=1010.0, upper=1010.0, forecast=False),
            _point(1, 990.0, lower=890.0, upper=1090.0, forecast=True),
            _point(2, 980.0, lower=830.0, upper=1130.0, forecast=True),
        ],
    )


def _series(options: dict[str, Any], name: str) -> dict[str, Any]:
    return next(s for s in options["series"] if s["name"] == name)


class TestTheAxisIsTime:
    def test_the_x_axis_is_time_not_category(self) -> None:
        # A category axis spaces points evenly whatever dates they carry, so
        # ninety days of history beside sixty forecast points came out
        # compressed — the past appeared to happen faster than the future.
        assert _forecast_chart(_result())["xAxis"]["type"] == "time"

    def test_every_point_carries_its_own_date(self) -> None:
        options = _forecast_chart(_result())
        actual = _series(options, "Actual")["data"]

        assert actual == [
            [str(TODAY - datetime.timedelta(days=2)), 1000.0],
            [str(TODAY - datetime.timedelta(days=1)), 1010.0],
        ]


class TestTheBandSurroundsThePrediction:
    def test_the_band_floor_is_the_lower_bound(self) -> None:
        options = _forecast_chart(_result())
        floor = _series(options, "Lower bound")["data"]

        assert [v for _, v in floor] == [890.0, 830.0]

    def test_the_band_height_is_the_interval(self) -> None:
        options = _forecast_chart(_result())
        band = _series(options, "Confidence band")["data"]

        assert [v for _, v in band] == [200.0, 300.0]

    def test_floor_plus_height_reaches_the_upper_bound(self) -> None:
        # Which is what "surrounds" means: the stack runs lower → upper, with
        # the prediction inside it, not above it.
        options = _forecast_chart(_result())
        floor = _series(options, "Lower bound")["data"]
        band = _series(options, "Confidence band")["data"]

        assert [f + b for (_, f), (_, b) in zip(floor, band, strict=True)] == [1090.0, 1130.0]

    def test_the_two_band_series_share_one_stack(self) -> None:
        options = _forecast_chart(_result())

        assert _series(options, "Lower bound")["stack"] == "confidence"
        assert _series(options, "Confidence band")["stack"] == "confidence"


class TestThePredictionMeetsTheHistory:
    def test_the_predicted_line_starts_where_the_actual_one_stops(self) -> None:
        # Two lines on a shared time axis leave a visible gap at today unless
        # the second one begins at the first one's last point.
        options = _forecast_chart(_result())
        actual = _series(options, "Actual")["data"]
        predicted = _series(options, "Predicted")["data"]

        assert predicted[0] == actual[-1]
        assert len(predicted) == 3


class TestScenarioMarkers:
    def test_today_is_marked_even_with_no_scenarios(self) -> None:
        marks = _series(_forecast_chart(_result()), "Predicted")["markLine"]["data"]

        assert [m["xAxis"] for m in marks] == [str(TODAY)]

    def test_a_scenario_adds_a_line_and_a_point_on_its_date(self) -> None:
        when = TODAY + datetime.timedelta(days=2)
        shift = ScenarioShift(label="Bonus", date=when, amount=5000.0)

        predicted = _series(_forecast_chart(_result(), scenarios=[shift]), "Predicted")

        assert [m["xAxis"] for m in predicted["markLine"]["data"]] == [str(TODAY), str(when)]
        assert predicted["markPoint"]["data"] == [
            {"coord": [str(when), 980.0], "name": "Bonus", "value": "Bonus"}
        ]

    def test_a_date_with_no_forecast_point_marks_but_pins_nothing(self) -> None:
        # `apply_scenarios` keys its deltas by exact date. This fixture's
        # forecast starts tomorrow, so today shifts nothing — the date is
        # still drawn, because the user put it there, but no pin claims a
        # bend that did not happen.
        shift = ScenarioShift(label="Today", date=TODAY, amount=1.0)

        predicted = _series(_forecast_chart(_result(), scenarios=[shift]), "Predicted")

        assert len(predicted["markLine"]["data"]) == 2
        assert predicted["markPoint"]["data"] == []

    def test_a_scenario_outside_the_forecast_marks_the_date_but_pins_nothing(self) -> None:
        # There is no line to pin a marker to out there; the date is still
        # worth drawing, because the user put it in.
        shift = ScenarioShift(label="Later", date=TODAY + datetime.timedelta(days=400), amount=1.0)

        predicted = _series(_forecast_chart(_result(), scenarios=[shift]), "Predicted")

        assert len(predicted["markLine"]["data"]) == 2
        assert predicted["markPoint"]["data"] == []


class TestTheBaselineReference:
    def test_no_baseline_series_when_none_is_given(self) -> None:
        names = [s["name"] for s in _forecast_chart(_result())["series"]]

        assert "Baseline (reference)" not in names

    def test_the_baseline_is_drawn_when_a_preset_moved_the_line(self) -> None:
        options = _forecast_chart(_result(), baseline=_result())

        assert _series(options, "Baseline (reference)")["lineStyle"]["type"] == "dotted"


class TestStaleAction:
    """When the page may say "press Re-run", and when it must not.

    This rule has been wrong three times — a mark that would not go away, one
    that outlived a failure and blamed the user for it, and one that erased
    "Insufficient transaction history" — and the Prophet branch that reaches
    it is not installed in this environment, so it is asserted directly.
    """

    def _act(self, **over: bool) -> str:
        args: dict[str, bool] = {
            "prophet_available": True,
            "drawn": True,
            "running": False,
            "controls_match": True,
        }
        args.update(over)
        return stale_action(**args)

    def test_a_chart_that_answers_the_controls_clears_the_mark(self) -> None:
        # Change the account and change it back: the hint has to go too.
        assert self._act(controls_match=True) == "clear"

    def test_controls_ahead_of_the_chart_are_marked(self) -> None:
        assert self._act(controls_match=False) == "mark"

    def test_the_naive_path_never_marks_anything(self) -> None:
        # Its re-run lands within the debounce; there is nothing to warn of.
        assert self._act(prophet_available=False, controls_match=False) == "leave"
        assert self._act(prophet_available=False, controls_match=True) == "leave"

    def test_nothing_is_said_while_a_run_is_in_flight(self) -> None:
        # The recorded account is still the previous run's, so a match here
        # would describe a chart that is not on screen.
        assert self._act(running=True, controls_match=True) == "leave"
        assert self._act(running=True, controls_match=False) == "leave"

    def test_a_page_with_nothing_drawn_keeps_the_message_it_has(self) -> None:
        # A failure, or too little history, under controls nobody touched:
        # the line already says something truer than "press Re-run", and it
        # is not the reader's doing.
        assert self._act(drawn=False, controls_match=True) == "leave"

    def test_but_that_message_stops_being_true_when_the_selection_moves(self) -> None:
        # "Insufficient transaction history" was about account A. Pick B and
        # it is no longer an answer to anything on screen.
        assert self._act(drawn=False, controls_match=False) == "mark"
