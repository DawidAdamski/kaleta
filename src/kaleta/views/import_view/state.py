# SPDX-License-Identifier: AGPL-3.0-or-later
"""Per-file queue state for the import wizard."""

from __future__ import annotations

from dataclasses import dataclass, field

from kaleta.services.import_service import (
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
    target_account_id: int | None = None
    expense_cat_id: int | None = None
    income_cat_id: int | None = None
    skip_duplicates: bool = True
    status: str = "pending"
    status_msg: str = ""
    imported_count: int = 0
    skipped_dupes: int = 0


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
    )


def apply_settings_snapshot(file: QueuedFile, snapshot: QueueSettingsSnapshot) -> None:
    """Copy inherited settings from a service snapshot back onto the file."""
    file.target_account_id = snapshot.target_account_id
    file.expense_cat_id = snapshot.expense_cat_id
    file.income_cat_id = snapshot.income_cat_id
    file.skip_duplicates = snapshot.skip_duplicates
