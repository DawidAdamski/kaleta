# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reading what the what-if builder was given, and saying it back.

The page's own edges, which the e2e pass exercises only down its happy path:
a Polish keyboard's decimal comma, a browser's non-breaking space, and the
inputs a reader can type that are not amounts at all.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest

from kaleta.exceptions import ValidationError
from kaleta.schemas.planned_transaction import RecurrenceFrequency
from kaleta.schemas.scenario import ScenarioDelta, ScenarioDeltaKind
from kaleta.views.wizard_scenarios import delta_summary, parse_amount, parse_date

TODAY = datetime.date(2026, 3, 1)


class TestParseAmount:
    @pytest.mark.parametrize(
        ("typed", "expected"),
        [
            ("-1500", "-1500"),
            ("2000.50", "2000.50"),
            # A Polish keyboard writes the decimal separator as a comma, and a
            # browser may hand back a thousands separator as a nbsp.
            ("-1500,75", "-1500.75"),
            ("40 000", "40000"),
            ("40 000,5", "40000.5"),
            ("  -30  ", "-30"),
        ],
    )
    def test_the_shapes_a_reader_actually_types(self, typed: str, expected: str) -> None:
        assert parse_amount(typed) == Decimal(expected)

    @pytest.mark.parametrize("typed", ["", None, "   ", "abc", "1.2.3", "--5", "40k"])
    def test_what_is_not_an_amount_is_refused_with_a_message(self, typed: object) -> None:
        with pytest.raises(ValidationError):
            parse_amount(typed)

    @pytest.mark.parametrize("typed", ["NaN", "Infinity", "-Infinity", "sNaN"])
    def test_a_number_that_is_not_a_quantity_is_refused(self, typed: str) -> None:
        """``Decimal`` parses these happily, and they poison everything after.

        A NaN makes every later comparison raise ``InvalidOperation`` — an
        ``ArithmeticError``, which the save handler does not catch, so the
        dialog would fail with no toast at all. An infinity would reach
        ``float()`` and the forecast arithmetic.
        """
        with pytest.raises(ValidationError):
            parse_amount(typed)


class TestParseDate:
    def test_an_iso_date_is_read(self) -> None:
        assert parse_date("2026-03-15") == datetime.date(2026, 3, 15)

    @pytest.mark.parametrize("typed", ["", None, "15.03.2026", "2026-13-01", "tomorrow"])
    def test_what_is_not_a_date_is_refused_with_a_message(self, typed: object) -> None:
        with pytest.raises(ValidationError):
            parse_date(typed)


class TestDeltaSummary:
    def test_a_percentage_keeps_its_sign_and_its_symbol(self) -> None:
        summary = delta_summary(
            ScenarioDelta(
                kind=ScenarioDeltaKind.INCOME_CHANGE,
                label="Pay cut",
                start_date=TODAY,
                percent=Decimal("-30"),
            )
        )

        assert "-30%" in summary
        assert "2026-03-01" in summary

    def test_an_amount_is_grouped_the_way_the_verdict_writes_it(self) -> None:
        summary = delta_summary(
            ScenarioDelta(
                kind=ScenarioDeltaKind.ONE_OFF,
                label="Car",
                start_date=TODAY,
                amount=Decimal("-40000"),
            )
        )

        assert "-40,000.00" in summary

    def test_a_recurring_delta_says_how_often(self) -> None:
        summary = delta_summary(
            ScenarioDelta(
                kind=ScenarioDeltaKind.RECURRING,
                label="Rent",
                start_date=TODAY,
                amount=Decimal("-4000"),
                cadence=RecurrenceFrequency.QUARTERLY,
            )
        )

        assert "quarterly" in summary
