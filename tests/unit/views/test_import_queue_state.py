# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for the import queue terminal-state helper.

Covers: KAL-CSV-020
"""

from __future__ import annotations

from kaleta.views.import_view.state import QueuedFile, queue_is_terminal


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
