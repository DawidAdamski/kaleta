# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for the import queue terminal-state helper.

Covers: KAL-CSV-020
"""

from __future__ import annotations

from kaleta.views.import_view.state import QueuedFile, leave_guard_active, queue_is_terminal


def _file(status: str) -> QueuedFile:
    return QueuedFile(id=status, filename=f"{status}.csv", content="", status=status)


def test_empty_queue_is_not_terminal() -> None:
    """Nothing to clear, so an upload must not trigger a reset."""
    assert queue_is_terminal([]) is False


def test_all_done_is_terminal() -> None:
    assert queue_is_terminal([_file("done")]) is True


def test_done_and_failed_is_terminal() -> None:
    """A failed file is finished too — it can never move back to Ready."""
    assert queue_is_terminal([_file("done"), _file("failed")]) is True


def test_done_and_ready_is_not_terminal() -> None:
    """A Ready file means the batch is still live: adding files keeps appending."""
    assert queue_is_terminal([_file("done"), _file("ready")]) is False


def test_importing_is_not_terminal() -> None:
    assert queue_is_terminal([_file("done"), _file("importing")]) is False


def test_pending_and_needs_mapping_are_not_terminal() -> None:
    assert queue_is_terminal([_file("pending")]) is False
    assert queue_is_terminal([_file("needs_mapping")]) is False


class TestLeaveGuardActive:
    """``leave_guard_active`` — when leaving /import would lose work.

    Covers: KAL-CSV-042
    """

    def test_empty_queue_has_nothing_to_lose(self) -> None:
        assert leave_guard_active([], importing=False) is False

    def test_a_file_waiting_to_be_imported_arms_the_guard(self) -> None:
        assert leave_guard_active([_file("ready")], importing=False) is True
        assert leave_guard_active([_file("needs_mapping")], importing=False) is True
        assert leave_guard_active([_file("done"), _file("pending")], importing=False) is True

    def test_a_finished_queue_clears_the_guard(self) -> None:
        assert leave_guard_active([_file("done"), _file("failed")], importing=False) is False

    def test_a_running_import_keeps_the_guard(self) -> None:
        assert leave_guard_active([_file("done")], importing=True) is True
