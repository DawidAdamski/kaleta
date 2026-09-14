# SPDX-License-Identifier: AGPL-3.0-or-later
"""The line under a pace bar, in both locales.

Covers: KAL-BUD-012, KAL-BUD-014 — the scenarios say "a line names the
amount and the date"; these pin what that line actually reads. The Polish
string is the one the pace column was widened for, and no e2e renders it.
"""

from __future__ import annotations

import datetime
import json
from decimal import Decimal
from pathlib import Path

from kaleta.services.budget_service import RealizationNote, RealizationNoteKind
from kaleta.views.budgets.realization import note_text

_LOCALES = Path("src/kaleta/i18n/locales")


def _template(locale: str, key: str) -> str:
    data = json.loads((_LOCALES / f"{locale}.json").read_text(encoding="utf-8"))
    return data["budgets"]["realization"][key]


class TestNoteText:
    def test_paid_in_full_reads_the_day_and_the_month(self) -> None:
        note = RealizationNote(RealizationNoteKind.PAID_IN_FULL, datetime.date(2026, 9, 1))

        assert note_text(note) == "Paid in full on 01.09 — expected"

    def test_planned_on_names_the_amount_and_the_day(self) -> None:
        note = RealizationNote(
            RealizationNoteKind.PLANNED_ON, datetime.date(2026, 9, 12), Decimal("284.00")
        )

        assert note_text(note) == "284.00 planned for 12.09"

    def test_a_thousand_keeps_its_separator(self) -> None:
        note = RealizationNote(
            RealizationNoteKind.PLANNED_ON, datetime.date(2026, 9, 12), Decimal("1284.00")
        )

        assert note_text(note) == "1,284.00 planned for 12.09"


class TestPolishTemplates:
    """The longest line the pace column has to hold."""

    def test_paid_in_full(self) -> None:
        assert (
            _template("pl", "note_paid_in_full").format(date="01.09")
            == "Opłacone w całości dnia 01.09 — zgodnie z planem"
        )

    def test_planned_on(self) -> None:
        assert (
            _template("pl", "note_planned_on").format(amount="284,00", date="12.09")
            == "284,00 zaplanowane na 12.09"
        )
