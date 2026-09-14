# SPDX-License-Identifier: AGPL-3.0-or-later
"""The "auto" mark on a mapping picker (artboard 2d).

Covers: KAL-CSV-025 — "the fields the importer recognised carry an auto mark,
and changing one of them by hand takes its mark away". The rule needs no
state of its own: a field is auto exactly while it still holds the guess.
"""

from __future__ import annotations

import json
import pathlib

import kaleta.i18n
from kaleta.i18n import plural_key
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


class TestRowCountPlural:
    """The caption's one number, in a language with three plural forms."""

    def test_english_needs_only_one_and_other(self) -> None:
        assert row_count_label(1) == "1 row"
        assert row_count_label(2) == "2 rows"
        assert row_count_label(1245) == "1,245 rows"

    def test_polish_few_covers_counts_ending_in_two_to_four(self) -> None:
        # "3 wierszy" is wrong Polish; the few form is what 2-4 take.
        forms = [plural_key("import.rows_count", n) for n in (2, 3, 4, 22, 104)]
        assert forms == ["import.rows_count_few"] * 5

    def test_the_teens_are_many_even_though_they_end_in_two_to_four(self) -> None:
        forms = [plural_key("import.rows_count", n) for n in (12, 13, 14, 112)]
        assert forms == ["import.rows_count_many"] * 4

    def test_one_is_singular_and_zero_is_not(self) -> None:
        assert plural_key("import.rows_count", 1) == "import.rows_count_one"
        assert plural_key("import.rows_count", 0) == "import.rows_count_many"
        assert plural_key("import.rows_count", 11) == "import.rows_count_many"

    def test_polish_really_carries_all_three_forms(self) -> None:
        locales = pathlib.Path(kaleta.i18n.__file__).parent / "locales"
        pl = json.loads((locales / "pl.json").read_text(encoding="utf-8"))["import"]
        assert pl["rows_count_one"] == "{count} wiersz"
        assert pl["rows_count_few"] == "{count} wiersze"
        assert pl["rows_count_many"] == "{count} wierszy"
