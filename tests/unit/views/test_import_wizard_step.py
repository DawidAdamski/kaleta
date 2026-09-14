# SPDX-License-Identifier: AGPL-3.0-or-later
"""Which step the import progress line points at (artboard 2d).

Covers: KAL-CSV-027 — the line has to agree with the page under it, and the
page decides what to show from the active file's status. Both read this.
"""

from __future__ import annotations

from kaleta.views.import_view.state import (
    STEP_CONFIRM,
    STEP_MAPPING,
    STEP_PREVIEW,
    STEP_SETTINGS,
    STEP_UPLOAD,
    QueuedFile,
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

    def test_an_imported_file_is_done(self) -> None:
        assert current_step(_file(status="done")) == STEP_CONFIRM

    def test_a_failed_generic_file_failed_at_its_mapping(self) -> None:
        assert current_step(_file(status="failed", profile="generic")) == STEP_MAPPING

    def test_a_failed_bank_file_failed_at_the_file_itself(self) -> None:
        # Nothing to map: a bank profile reads its own columns, so the thing
        # that went wrong was the upload.
        assert current_step(_file(status="failed", profile="mbank")) == STEP_UPLOAD
