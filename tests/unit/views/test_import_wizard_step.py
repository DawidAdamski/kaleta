# SPDX-License-Identifier: AGPL-3.0-or-later
"""Which step the import progress line points at (artboard 2d).

Covers: KAL-CSV-027 — the line has to agree with the page under it, and the
page decides what to show from the active file's status. Both read this.
"""

from __future__ import annotations

from kaleta.services.import_service import (
    ColumnMapping,
    MBankFileMetadata,
    QueueSettingsSnapshot,
)
from kaleta.views.import_view.state import (
    STEP_CONFIRM,
    STEP_MAPPING,
    STEP_PREVIEW,
    STEP_SETTINGS,
    STEP_UPLOAD,
    QueuedFile,
    apply_settings_snapshot,
    current_step,
)


def _mbank_metadata(currency: str) -> MBankFileMetadata:
    return MBankFileMetadata(
        client_name="Jan Kowalski",
        account_type="eKonto",
        currency=currency,
        account_number="55 1140 2004 0000 3302 7888 6836",
        account_number_digits="55114020040000330278886836",
        date_from=None,
        date_to=None,
    )


def _file(**kwargs: object) -> QueuedFile:
    file = QueuedFile(id="f1", filename="statement.csv", content="")
    for key, value in kwargs.items():
        setattr(file, key, value)
    return file


class TestCurrentStep:
    def test_an_empty_queue_is_waiting_for_a_file(self) -> None:
        assert current_step(None) == STEP_UPLOAD

    def test_a_file_still_parsing_is_part_of_the_upload(self) -> None:
        assert current_step(_file(status="pending")) == STEP_UPLOAD

    def test_a_file_that_needs_its_columns_is_on_the_mapping_step(self) -> None:
        assert current_step(_file(status="needs_mapping")) == STEP_MAPPING

    def test_a_parsed_file_with_nowhere_to_go_is_on_settings(self) -> None:
        assert current_step(_file(status="ready")) == STEP_SETTINGS

    def test_a_parsed_file_with_every_setting_chosen_is_on_preview(self) -> None:
        ready = _file(status="ready", target_account_id=7, expense_cat_id=1, income_cat_id=2)
        assert current_step(ready) == STEP_PREVIEW

    def test_an_account_without_categories_has_not_finished_settings(self) -> None:
        # The Import button refuses with select_expense_cat_hint until both
        # defaults are chosen, so ticking settings here would have the line
        # claiming a step the page below it is still asking for.
        assert current_step(_file(status="ready", target_account_id=7)) == STEP_SETTINGS
        half = _file(status="ready", target_account_id=7, expense_cat_id=1)
        assert current_step(half) == STEP_SETTINGS

    def test_a_currency_the_account_disagrees_with_keeps_settings_current(self) -> None:
        # The Import button refuses a PLN account for an EUR statement, and
        # the account it disagrees with is chosen on this very card — so the
        # step the user still has to do is settings, not preview.
        ready = _file(
            status="ready",
            profile="mbank",
            target_account_id=7,
            expense_cat_id=1,
            income_cat_id=2,
            metadata=_mbank_metadata("EUR"),
        )
        assert current_step(ready, account_currency="PLN") == STEP_SETTINGS
        assert current_step(ready, account_currency="EUR") == STEP_PREVIEW
        # And with no account currency to hand there is nothing to disagree
        # with, which is the same answer the readiness check gives.
        assert current_step(ready) == STEP_PREVIEW

    def test_categories_without_an_account_are_not_enough_either(self) -> None:
        part = _file(status="ready", expense_cat_id=1, income_cat_id=2)
        assert current_step(part) == STEP_SETTINGS

    def test_a_file_being_imported_has_not_gone_backwards(self) -> None:
        # A bulk import repaints whenever the user clicks another queue file,
        # and falling through to the default would send the line from preview
        # back to upload while the rows are going in.
        assert current_step(_file(status="importing")) == STEP_PREVIEW

    def test_an_imported_file_is_done(self) -> None:
        assert current_step(_file(status="done")) == STEP_CONFIRM

    def test_a_failed_file_stands_on_the_upload_step(self) -> None:
        # The page hides the mapping, settings and preview cards for a failed
        # file, so pointing the line at any of them would name a step that is
        # not on screen. True whichever profile read it.
        assert current_step(_file(status="failed", profile="generic")) == STEP_UPLOAD
        assert current_step(_file(status="failed", profile="mbank")) == STEP_UPLOAD


class TestInheritedMappingIsStillAuto:
    """Covers: KAL-CSV-025 — the mark follows the importer, not one source.

    Scope calls the marked fields the ones filled "by profile match or
    heuristic". A mapping copied from another file in the queue is the
    importer filling them in too, so it carries the marks a fresh detection
    would; the user's own edits never do.
    """

    def test_an_inherited_mapping_is_recorded_as_the_importers_own(self) -> None:
        file = _file(status="ready")
        assert file.auto_mapping is None

        mapping = ColumnMapping(date=0, amount=1, description=2)
        apply_settings_snapshot(
            file, QueueSettingsSnapshot(file_id=file.id, profile="generic", column_mapping=mapping)
        )

        assert file.column_mapping == mapping
        assert file.auto_mapping == mapping

    def test_inheriting_nothing_leaves_the_marks_alone(self) -> None:
        file = _file(status="ready")
        file.auto_mapping = ColumnMapping(date=0)

        apply_settings_snapshot(file, QueueSettingsSnapshot(file_id=file.id, profile="generic"))

        assert file.auto_mapping == ColumnMapping(date=0)
