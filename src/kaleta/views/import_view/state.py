# SPDX-License-Identifier: AGPL-3.0-or-later
"""Per-file queue state for the import wizard."""

from __future__ import annotations

from dataclasses import dataclass, field

from kaleta.schemas.transaction import TransactionCreate
from kaleta.services.import_service import (
    ColumnMapping,
    CsvInspection,
    MBankFileMetadata,
    ParsedRow,
    QueueSettingsSnapshot,
)


@dataclass
class QueuedFile:
    id: str
    filename: str
    content: str
    profile: str = "generic"
    parsed_rows: list[ParsedRow] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)
    metadata: MBankFileMetadata | None = None
    column_mapping: ColumnMapping | None = None
    inspection: CsvInspection | None = None
    target_account_id: int | None = None
    expense_cat_id: int | None = None
    income_cat_id: int | None = None
    skip_duplicates: bool = True
    status: str = "pending"
    status_msg: str = ""
    imported_count: int = 0
    skipped_dupes: int = 0
    skipped_rows: list[TransactionCreate] = field(default_factory=list)
    matched_rule_id: int | None = None
    matched_rule_pattern: str | None = None
    remember_mapping: bool = True
    filename_pattern: str = ""
    from_bulk_default: bool = False


TERMINAL_STATUSES = frozenset({"done", "failed"})


def queue_is_terminal(queue: list[QueuedFile]) -> bool:
    """True when the queue holds files and every one of them has finished.

    A fully ``done``/``failed`` queue is a completed import session. The next
    upload starts a fresh one rather than piling onto rows that can no longer
    be imported. An empty queue is not terminal — there is nothing to clear.
    """
    return bool(queue) and all(f.status in TERMINAL_STATUSES for f in queue)


def settings_snapshot(file: QueuedFile) -> QueueSettingsSnapshot:
    """Convert queue file state into a service-layer settings snapshot."""
    return QueueSettingsSnapshot(
        file_id=file.id,
        profile=file.profile,
        metadata=file.metadata,
        target_account_id=file.target_account_id,
        expense_cat_id=file.expense_cat_id,
        income_cat_id=file.income_cat_id,
        skip_duplicates=file.skip_duplicates,
        column_mapping=file.column_mapping,
    )


def apply_settings_snapshot(file: QueuedFile, snapshot: QueueSettingsSnapshot) -> None:
    """Copy inherited settings from a service snapshot back onto the file."""
    file.target_account_id = snapshot.target_account_id
    file.expense_cat_id = snapshot.expense_cat_id
    file.income_cat_id = snapshot.income_cat_id
    file.skip_duplicates = snapshot.skip_duplicates
    if snapshot.column_mapping is not None:
        file.column_mapping = snapshot.column_mapping


def import_button_label(ready_count: int) -> str:
    """Count-aware label for the queue import button."""
    from kaleta.i18n import t

    if ready_count <= 0:
        return t("import.import_btn_zero")
    if ready_count == 1:
        return t("import.import_btn_one")
    return t("import.import_btn_many", count=ready_count)
