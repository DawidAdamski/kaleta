# SPDX-License-Identifier: AGPL-3.0-or-later
"""Per-file queue state for the import wizard."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from kaleta.schemas.transaction import TransactionCreate
from kaleta.services.import_service import (
    ColumnMapping,
    CsvInspection,
    ImportReadinessCheck,
    MBankFileMetadata,
    ParsedRow,
    QueueSettingsSnapshot,
    validate_import_readiness,
)


@dataclass
class QueuedFile:
    id: str
    filename: str
    content: str
    #: The upload's undecoded bytes. Only a binary format needs them — XLSX is
    #: a ZIP, so ``content`` holds nothing readable for one — and every text
    #: format ignores them.
    raw: bytes = b""
    #: The encoding the upload decoded as, named in the mapping caption.
    encoding: str = "UTF-8"
    profile: str = "generic"
    parsed_rows: list[ParsedRow] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)
    metadata: MBankFileMetadata | None = None
    column_mapping: ColumnMapping | None = None
    #: The mapping the importer filled in by itself — header detection, a
    #: saved rule, or another queued file — never the user's own edits. The
    #: "auto" marks are what is left of it in the pickers.
    auto_mapping: ColumnMapping | None = None
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
    #: Line numbers that could not be parsed, for the mapping step's warning.
    error_rows: list[int] = field(default_factory=list)


TERMINAL_STATUSES = frozenset({"done", "failed"})

#: The six steps the progress line draws, in order. 1-based, because the line
#: numbers them for the reader.
STEP_FORMAT = 1
STEP_UPLOAD = 2
STEP_MAPPING = 3
STEP_SETTINGS = 4
STEP_PREVIEW = 5
STEP_CONFIRM = 6


def current_step(active: QueuedFile | None, *, account_currency: str | None = None) -> int:
    """Which of the six steps the *work* is on.

    The conditions are the ones each section uses to decide whether it
    applies to this file, in one place — so the progress line cannot
    disagree with the page under it. Since `restyle-import-wizard` the page
    shows one step at a time and this is its ceiling: the reader may stand
    anywhere up to here (see ``views.import_view.wizard``), and the shell
    puts them here whenever the page, rather than the reader, is choosing.

    A bank profile (mbank, pko, wise) never shows the mapping card, and its
    node still reads as done once the file is parsed. That is not a lie: the
    columns *were* mapped — by the profile rather than by hand — so the step
    is behind the user, which is what a done node means.
    """
    if active is None:
        return STEP_UPLOAD
    if active.status == "done":
        return STEP_CONFIRM
    if active.status == "importing":
        # The rows are going in: the preview is behind the user and the
        # confirmation is not there yet. Without this the line would drop
        # back to upload the moment a bulk import repaints — clicking another
        # queue file mid-import does exactly that.
        return STEP_PREVIEW
    if active.status == "needs_mapping":
        return STEP_MAPPING
    if active.status == "failed":
        # A failed file shows no mapping, settings or preview card — the page
        # hides all three — so the only place left to stand is the upload.
        return STEP_UPLOAD
    if active.status == "ready":
        # Ready means parsed, and both cards are on screen. The step is what
        # the user still has to *do*: say where the rows go, then look at
        # them. An account alone is not "where they go" — the import is
        # blocked until both default categories are chosen too, and ticking
        # settings while the Import button refuses is the line lying about
        # the page under it.
        complete = settings_are_complete(active, account_currency=account_currency)
        return STEP_PREVIEW if complete else STEP_SETTINGS
    return STEP_UPLOAD


def settings_are_complete(file: QueuedFile, *, account_currency: str | None = None) -> bool:
    """Everything the settings step asks for, chosen.

    Asked of ``validate_import_readiness`` rather than copied from it: the
    settings node is ticked exactly when the Import button would stop
    refusing, so a rule added to the service later cannot leave the line
    claiming a step the page below it is still asking for.

    That includes a currency mismatch, which is a settings problem after
    all — the account it disagrees with is chosen on this very card. The
    caller passes the chosen account's currency; without one there is
    nothing to disagree with.
    """
    return settings_block_reason(file, account_currency=account_currency) is None


def settings_block_reason(
    file: QueuedFile, *, account_currency: str | None = None
) -> tuple[str, dict[str, Any]] | None:
    """What the settings step is still missing, as ``(i18n key, params)``.

    ``None`` when nothing is. This is the message the footer puts beside a
    refusing ``Continue``: "Choose an account", not the file's last piece of
    news ("Loaded 2 rows."), which answers a question nobody asked.
    """
    error_key, params = validate_import_readiness(
        ImportReadinessCheck(
            target_account_id=file.target_account_id,
            expense_cat_id=file.expense_cat_id,
            income_cat_id=file.income_cat_id,
            profile=file.profile,
            metadata=file.metadata,
            account_currency=account_currency,
        )
    )
    return None if error_key is None else (error_key, params)


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
        # Inherited, not typed: it carries the marks a fresh detection would.
        file.auto_mapping = snapshot.column_mapping


def import_button_label(ready_count: int) -> str:
    """Count-aware label for the queue import button."""
    from kaleta.i18n import t

    if ready_count <= 0:
        return t("import.import_btn_zero")
    if ready_count == 1:
        return t("import.import_btn_one")
    return t("import.import_btn_many", count=ready_count)
