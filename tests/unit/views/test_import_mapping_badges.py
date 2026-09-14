# SPDX-License-Identifier: AGPL-3.0-or-later
"""The "auto" mark on a mapping picker (artboard 2d).

Covers: KAL-CSV-025 — "the fields the importer recognised carry an auto mark,
and changing one of them by hand takes its mark away". The rule needs no
state of its own: a field is auto exactly while it still holds the guess.
"""

from __future__ import annotations

from kaleta.services.import_service import ColumnMapping, row_error_line, row_error_prefix
from kaleta.views.import_view.mapping_section import (
    SAMPLE_CELL_CHARS,
    _col_options,
    auto_detected_fields,
    column_label,
    message_is_summarised,
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


class TestMessageProminence:
    """Which parse messages the warning strip above already speaks for."""

    def test_a_message_naming_a_listed_row_is_detail(self) -> None:
        msg = f"{row_error_prefix(3)} Invalid amount: NOT_A_NUMBER"
        assert message_is_summarised(msg, [3, 5]) is True

    def test_a_blocking_message_keeps_its_prominence_beside_row_errors(self) -> None:
        # The case the old `bool(error_rows)` flag got wrong: one failing row
        # muted every message, including the one nothing else was saying.
        assert message_is_summarised("Date column is required", [3, 5]) is False

    def test_a_row_the_strip_does_not_list_is_not_summarised(self) -> None:
        msg = f"{row_error_prefix(9)} Invalid date"
        assert message_is_summarised(msg, [3, 5]) is False

    def test_nothing_is_summarised_when_no_row_failed(self) -> None:
        assert message_is_summarised("Date column is required", []) is False

    def test_a_row_error_reads_back_the_line_it_names(self) -> None:
        # The pair the prominence rule rests on: what the service writes is
        # what the view reads, without either side spelling out the format.
        assert row_error_line(f"{row_error_prefix(42)} Invalid date") == 42

    def test_a_message_naming_no_row_reads_back_as_none(self) -> None:
        assert row_error_line("Date column is required") is None


class TestColumnLabel:
    """The sample table and the pickers name the same column the same way."""

    def test_a_named_column_is_numbered_and_named(self) -> None:
        assert column_label(0, " Data ") == "1: Data"

    def test_a_blank_header_still_gets_a_name(self) -> None:
        # The case the two used to disagree on: the sample said "3", the
        # picker said "3: Column 3".
        assert column_label(2, "   ") == "3: Column 3"

    def test_the_picker_and_the_sample_agree_on_a_blank_header(self) -> None:
        headers = ["date", "amount", "  "]
        options = _col_options(headers)

        assert [options[i] for i in range(len(headers))] == [
            column_label(i, h) for i, h in enumerate(headers)
        ]
