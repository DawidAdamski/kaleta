# SPDX-License-Identifier: AGPL-3.0-or-later
"""The "auto" mark on a mapping picker (artboard 2d).

Covers: KAL-CSV-025 — "the fields the importer recognised carry an auto mark,
and changing one of them by hand takes its mark away". The rule needs no
state of its own: a field is auto exactly while it still holds the guess.
"""

from __future__ import annotations

from kaleta.services.import_service import ColumnMapping
from kaleta.views.import_view.mapping_section import (
    SAMPLE_CELL_CHARS,
    auto_detected_fields,
    row_count_label,
    truncate_cell,
)


class TestAutoDetectedFields:
    def test_a_field_holding_the_guess_is_auto(self) -> None:
        detected = ColumnMapping(date=0, amount=1, description=2)

        assert auto_detected_fields(detected, detected) == frozenset(
            {"date", "amount", "description"}
        )

    def test_a_field_changed_by_hand_is_not(self) -> None:
        detected = ColumnMapping(date=0, amount=1, description=2)
        current = ColumnMapping(date=0, amount=1, description=5)

        assert auto_detected_fields(detected, current) == frozenset({"date", "amount"})

    def test_a_field_the_importer_never_guessed_is_not_auto(self) -> None:
        # Detection leaves payee alone; the user picking column 3 for it is a
        # choice, not a guess to take credit for.
        detected = ColumnMapping(date=0)
        current = ColumnMapping(date=0, payee=3)

        assert auto_detected_fields(detected, current) == frozenset({"date"})

    def test_nothing_inspected_means_nothing_to_mark(self) -> None:
        assert auto_detected_fields(None, ColumnMapping(date=0)) == frozenset()
        assert auto_detected_fields(ColumnMapping(date=0), None) == frozenset()

    def test_an_unmapped_field_is_never_auto(self) -> None:
        assert auto_detected_fields(ColumnMapping(), ColumnMapping()) == frozenset()


class TestTruncateCell:
    def test_a_short_value_is_left_alone(self) -> None:
        assert truncate_cell("  Biedronka  ") == "Biedronka"

    def test_a_long_value_is_cut_with_an_ellipsis(self) -> None:
        value = "A" * 60
        cut = truncate_cell(value)

        assert len(cut) == SAMPLE_CELL_CHARS
        assert cut.endswith("…")


class TestRowCountLabel:
    """What the caption actually prints, in the app's number format."""

    def test_english_singular_and_plural(self) -> None:
        assert row_count_label(1) == "1 row"
        assert row_count_label(2) == "2 rows"

    def test_the_thousands_separator_is_the_app_s(self) -> None:
        assert row_count_label(1245) == "1,245 rows"
