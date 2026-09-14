# SPDX-License-Identifier: AGPL-3.0-or-later
"""Which step the import progress line points at (artboard 2d).

Covers: KAL-CSV-027 — the line has to agree with the page under it, and the
page decides what to show from the active file's status. Both read this.
"""

from __future__ import annotations

from kaleta.services.import_service import ColumnMapping, QueueSettingsSnapshot
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

    def test_a_parsed_file_with_an_account_is_on_preview(self) -> None:
        assert current_step(_file(status="ready", target_account_id=7)) == STEP_PREVIEW

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
