"""Unified import view — generic CSV and bank-specific profiles in one page.

Multi-file queue: drop N files, switch focus between them, Import All runs
sequentially and surfaces a per-file summary.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from nicegui import events, ui

from kaleta.db import AsyncSessionFactory
from kaleta.i18n import t
from kaleta.models.category import Category
from kaleta.services import AccountService, CategoryService, TransactionService
from kaleta.services.import_service import (
    ImportResult,
    ImportService,
    MBankFileMetadata,
    MBankPreprocessor,
    ParsedRow,
)
from kaleta.views.layout import page_layout


def _build_cat_opts(cats_list: list[Category]) -> dict[int, str]:
    """Build {id: label} with hierarchical labels like 'Food → Groceries'."""
    cats_by_id = {c.id: c for c in cats_list}
    result: dict[int, str] = {}
    roots = sorted(
        [c for c in cats_list if c.parent_id is None or c.parent_id not in cats_by_id],
        key=lambda c: c.name,
    )
    for root in roots:
        result[root.id] = root.name
        children = sorted([c for c in cats_list if c.parent_id == root.id], key=lambda c: c.name)
        for child in children:
            result[child.id] = f"{root.name} → {child.name}"
    return result


# ── Bank profiles ─────────────────────────────────────────────────────────────
_PROFILES: list[tuple[str, str, str, bool]] = [
    ("generic", "import.profile_generic", "table_chart", True),
    ("mbank", "import.profile_mbank", "account_balance", True),
]


def _auto_decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp1250", "iso-8859-2"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


# ── Per-file state ────────────────────────────────────────────────────────────


@dataclass
class QueuedFile:
    id: str
    filename: str
    content: str
    profile: str = "generic"
    parsed_rows: list[ParsedRow] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)
    metadata: MBankFileMetadata | None = None
    # settings
    target_account_id: int | None = None
    expense_cat_id: int | None = None
    income_cat_id: int | None = None
    skip_duplicates: bool = True
    # status
    status: str = "pending"  # pending | ready | importing | done | failed | skipped
    status_msg: str = ""
    # result
    imported_count: int = 0
    skipped_dupes: int = 0


_STATUS_COLOR: dict[str, str] = {
    "pending": "grey-6",
    "ready": "primary",
    "importing": "amber-7",
    "done": "positive",
    "failed": "negative",
    "skipped": "grey-6",
}


def register() -> None:
    @ui.page("/import")
    async def import_page() -> None:
        async with AsyncSessionFactory() as session:
            accounts = await AccountService(session).list()
            categories = await CategoryService(session).list()

        account_options = {a.id: f"{a.name} ({a.currency})" for a in accounts}
        expense_cat_opts = _build_cat_opts([c for c in categories if c.type.value == "expense"])
        income_cat_opts = _build_cat_opts([c for c in categories if c.type.value == "income"])

        state: dict[str, Any] = {
            "queue": [],  # list[QueuedFile]
            "active_id": None,  # str | None
        }

        def _active() -> QueuedFile | None:
            aid = state["active_id"]
            if aid is None:
                return None
            return next((f for f in state["queue"] if f.id == aid), None)

        with page_layout(t("import.title")):
            ui.label(t("import.title")).classes("text-2xl font-bold")

            # ── Step indicator ────────────────────────────────────────────────
            _steps = [
                t("import.step_format"),
                t("import.step_upload"),
                t("import.step_settings"),
                t("import.step_preview"),
                t("import.step_confirm"),
            ]
            with ui.row().classes("w-full items-center gap-0 mb-2"):
                for i, step_label in enumerate(_steps):
                    num = i + 1
                    with ui.row().classes("items-center gap-1"):
                        ui.label(str(num)).classes(
                            "text-xs font-bold rounded-full w-6 h-6 flex items-center "
                            "justify-center bg-primary text-white"
                        )
                        ui.label(step_label).classes("text-sm text-grey-7 font-medium")
                    if i < len(_steps) - 1:
                        ui.label("→").classes("text-grey-4 mx-2 text-sm")

            # ══════════════════════════════════════════════════════════════════
            # SECTION 1 — Profile selector (applies to the active file)
            # ══════════════════════════════════════════════════════════════════
            with ui.card().classes("w-full"):
                ui.label(t("import.profile_label")).classes(
                    "text-sm text-grey-6 font-medium uppercase tracking-wide mb-3"
                )
                with ui.row().classes("gap-3 flex-wrap"):
                    profile_btns: dict[str, ui.button] = {}

                    async def _select_profile(key: str) -> None:
                        f = _active()
                        if f is None:
                            return
                        f.profile = key
                        # Re-parse with the new profile
                        await _parse_file(f)
                        _repaint_active()
                        _render_queue()

                    for profile_key, label_key, icon, enabled in _PROFILES:
                        btn = ui.button(
                            t(label_key),
                            icon=icon,
                            on_click=lambda k=profile_key: _select_profile(k),
                        ).props("color=grey-4 flat")
                        if not enabled:
                            btn.props("disable")
                            btn.tooltip(t("import.profile_coming_soon"))
                        profile_btns[profile_key] = btn

            # ══════════════════════════════════════════════════════════════════
            # SECTION 2 — Upload (multi-file)
            # ══════════════════════════════════════════════════════════════════
            with ui.card().classes("w-full"):
                ui.label(t("import.upload_section")).classes("text-lg font-semibold mb-1")
                upload_hint_label = ui.label(t("import.upload_hint_generic")).classes(
                    "text-sm text-grey-6 mb-3"
                )

                upload_widget = (
                    ui.upload(
                        label=t("import.drop_hint_generic"),
                        auto_upload=True,
                        multiple=True,
                        max_files=20,
                    )
                    .props("accept=.csv flat bordered")
                    .classes("w-full mt-2")
                )

            # ══════════════════════════════════════════════════════════════════
            # SECTION 3 — Queue panel + Import all
            # ══════════════════════════════════════════════════════════════════
            with ui.card().classes("w-full"):
                with ui.row().classes("w-full items-center justify-between mb-2"):
                    ui.label(t("import.queue_section")).classes("text-lg font-semibold")
                    import_all_btn = ui.button(
                        t("import.import_all"), icon="upload"
                    ).props("color=primary unelevated")
                ui.label(t("import.queue_active_hint")).classes("text-xs text-grey-6 mb-2")
                queue_container = ui.column().classes("w-full gap-1")

            # ══════════════════════════════════════════════════════════════════
            # SECTION 4 — mBank metadata banner (per-active-file)
            # ══════════════════════════════════════════════════════════════════
            meta_card = ui.card().classes("k-info-banner w-full bg-blue-50")
            meta_card.set_visibility(False)
            with meta_card:
                meta_grid = ui.grid(columns=2).classes("w-full gap-x-6 gap-y-1")

            # ══════════════════════════════════════════════════════════════════
            # SECTION 5 — Settings (active file)
            # ══════════════════════════════════════════════════════════════════
            settings_card = ui.card().classes("w-full")
            settings_card.set_visibility(False)
            with settings_card:
                ui.label(t("import.settings_section")).classes("text-lg font-semibold mb-3")

                auto_match_label = ui.label("").classes("text-sm text-green-700")
                currency_warn_label = ui.label("").classes("text-sm text-amber-600")

                with ui.row().classes("w-full gap-4 flex-wrap"):
                    account_sel = ui.select(
                        account_options, label=t("import.target_account")
                    ).classes("flex-1 min-w-64")

                    expense_cat_sel = ui.select(
                        expense_cat_opts, label=t("import.default_expense_cat")
                    ).classes("flex-1 min-w-48")
                    income_cat_sel = ui.select(
                        income_cat_opts, label=t("import.default_income_cat")
                    ).classes("flex-1 min-w-48")

                skip_dupes_cb = ui.checkbox(t("import.skip_duplicates"), value=True)

                def _check_currency(_e: object = None) -> None:
                    f = _active()
                    if f is None or f.metadata is None:
                        currency_warn_label.set_text("")
                        return
                    acc = next((a for a in accounts if a.id == account_sel.value), None)
                    if acc and acc.currency.upper() != f.metadata.currency.upper():
                        currency_warn_label.set_text(
                            t(
                                "import.currency_mismatch",
                                file=f.metadata.currency,
                                account=acc.currency,
                            )
                        )
                    else:
                        currency_warn_label.set_text("")

                def _on_account_change(_e: object = None) -> None:
                    f = _active()
                    if f is None:
                        return
                    f.target_account_id = account_sel.value
                    _check_currency()

                def _on_expense_change(_e: object = None) -> None:
                    f = _active()
                    if f is None:
                        return
                    f.expense_cat_id = expense_cat_sel.value

                def _on_income_change(_e: object = None) -> None:
                    f = _active()
                    if f is None:
                        return
                    f.income_cat_id = income_cat_sel.value

                def _on_skip_change(_e: object = None) -> None:
                    f = _active()
                    if f is None:
                        return
                    f.skip_duplicates = bool(skip_dupes_cb.value)

                account_sel.on("update:model-value", _on_account_change)
                expense_cat_sel.on("update:model-value", _on_expense_change)
                income_cat_sel.on("update:model-value", _on_income_change)
                skip_dupes_cb.on("update:model-value", _on_skip_change)

            # ══════════════════════════════════════════════════════════════════
            # SECTION 6 — Preview (active file)
            # ══════════════════════════════════════════════════════════════════
            preview_card = ui.card().classes("w-full")
            preview_card.set_visibility(False)
            with preview_card:
                ui.label(t("import.preview_section")).classes("text-lg font-semibold mb-1")
                ui.label(t("import.preview_hint")).classes("text-xs text-grey-6 mb-2")

                stats_row = ui.row().classes("gap-3 mb-3")

                preview_table = (
                    ui.table(
                        columns=[
                            {
                                "name": "date",
                                "label": t("common.date"),
                                "field": "date",
                                "align": "left",
                            },
                            {
                                "name": "amount",
                                "label": t("common.amount"),
                                "field": "amount",
                                "align": "right",
                            },
                            {
                                "name": "description",
                                "label": t("common.description"),
                                "field": "description",
                                "align": "left",
                            },
                            {
                                "name": "type",
                                "label": t("common.type"),
                                "field": "type",
                                "align": "left",
                            },
                        ],
                        rows=[],
                        row_key="idx",
                    )
                    .classes("w-full")
                    .props("dense")
                )

            # ══════════════════════════════════════════════════════════════════
            # SECTION 7 — Internal transfer detection (generic only)
            # ══════════════════════════════════════════════════════════════════
            transfer_card = ui.card().classes("w-full")
            transfer_card.set_visibility(False)
            with transfer_card:
                ui.label(t("import.transfer_section")).classes("text-lg font-semibold mb-1")
                ui.label(t("import.transfer_hint")).classes("text-sm text-grey-6 mb-3")
                transfer_result = ui.label("").classes("text-sm text-green-700")

                async def run_detect() -> None:
                    async with AsyncSessionFactory() as session:
                        pairs = await ImportService(session).detect_and_link_transfers()
                    msg = t("import.linked_pairs", count=pairs)
                    transfer_result.set_text(msg)
                    ui.notify(msg, type="positive")

                ui.button(
                    t("import.detect_transfers"),
                    icon="compare_arrows",
                    on_click=run_detect,
                ).props("color=secondary")

            # ══════════════════════════════════════════════════════════════════
            # SECTION 8 — Summary (shown after Import All)
            # ══════════════════════════════════════════════════════════════════
            summary_card = ui.card().classes("w-full")
            summary_card.set_visibility(False)
            with summary_card:
                ui.label(t("import.summary_heading")).classes("text-lg font-semibold mb-2")
                summary_container = ui.column().classes("w-full gap-1")
                summary_totals = ui.label("").classes("text-sm font-semibold mt-2")

            # ── Helpers ───────────────────────────────────────────────────────

            def _is_transfer_row(r: ParsedRow) -> bool:
                known: set[str] = {
                    re.sub(r"\D", "", a.external_account_number)
                    for a in accounts
                    if a.external_account_number
                }
                digits = re.sub(r"\D", "", r.raw.get("Numer rachunku", ""))
                return bool(digits and digits in known)

            async def _parse_file(f: QueuedFile) -> None:
                """Parse a file's content against its current profile, updating in place."""
                f.parsed_rows = []
                f.parse_errors = []
                f.metadata = None
                f.status_msg = ""

                # Auto-detect mBank on first parse (unless user already picked generic)
                if f.profile == "generic" and MBankPreprocessor.is_mbank_file(f.content):
                    f.profile = "mbank"

                async with AsyncSessionFactory() as session:
                    svc = ImportService(session)
                    if f.profile == "mbank":
                        if not MBankPreprocessor.is_mbank_file(f.content):
                            f.status = "failed"
                            f.status_msg = t("import.not_mbank_file")
                            return
                        data_section = MBankPreprocessor.extract_data_section(f.content)
                        if data_section is None:
                            f.status = "failed"
                            f.status_msg = t("import.no_data_section")
                            return
                        f.metadata = MBankPreprocessor.extract_metadata(f.content)
                        result: ImportResult = svc.parse_csv(data_section, delimiter=";")
                    else:
                        result = svc.parse_csv(f.content)

                f.parsed_rows = result.rows
                f.parse_errors = result.errors
                if not f.parsed_rows:
                    f.status = "failed"
                    f.status_msg = t("import.no_rows", skipped=result.skipped)
                    return
                f.status = "ready"
                f.status_msg = t("import.rows_loaded", count=len(f.parsed_rows))

            def _inherit_settings(f: QueuedFile) -> bool:
                """Copy settings from the most recent prior file with a match.

                Match precedence:
                  1. Same mBank account digits → inherit everything.
                  2. Same profile → inherit categories + skip_duplicates only.
                Returns True when something was inherited.
                """
                # 1. mBank account-digit match
                if f.profile == "mbank" and f.metadata and f.metadata.account_number_digits:
                    for prior in reversed(state["queue"]):
                        if prior.id == f.id:
                            continue
                        if (
                            prior.profile == "mbank"
                            and prior.metadata
                            and prior.metadata.account_number_digits
                            == f.metadata.account_number_digits
                            and prior.target_account_id is not None
                        ):
                            f.target_account_id = prior.target_account_id
                            f.expense_cat_id = prior.expense_cat_id
                            f.income_cat_id = prior.income_cat_id
                            f.skip_duplicates = prior.skip_duplicates
                            return True
                # 2. Same-profile category inheritance
                for prior in reversed(state["queue"]):
                    if prior.id == f.id:
                        continue
                    if prior.profile == f.profile and (
                        prior.expense_cat_id or prior.income_cat_id
                    ):
                        if f.expense_cat_id is None:
                            f.expense_cat_id = prior.expense_cat_id
                        if f.income_cat_id is None:
                            f.income_cat_id = prior.income_cat_id
                        f.skip_duplicates = prior.skip_duplicates
                        return True
                return False

            async def _auto_match_account(f: QueuedFile) -> bool:
                """For mBank files, match the target account by external number."""
                if f.profile != "mbank" or not f.metadata:
                    return False
                digits = f.metadata.account_number_digits
                if not digits:
                    return False
                async with AsyncSessionFactory() as session:
                    matched = await AccountService(session).find_by_external_number(
                        digits[-10:]
                    )
                if matched and matched.id in account_options:
                    f.target_account_id = matched.id
                    return True
                return False

            def _repaint_active() -> None:
                """Sync the per-file UI widgets to the active file's state."""
                f = _active()

                # Profile button highlight
                for k, btn in profile_btns.items():
                    is_active = f is not None and f.profile == k
                    btn.props(
                        "color=primary unelevated"
                        if is_active
                        else "color=grey-4 flat"
                    )

                if f is None:
                    meta_card.set_visibility(False)
                    settings_card.set_visibility(False)
                    preview_card.set_visibility(False)
                    transfer_card.set_visibility(False)
                    upload_hint_label.set_text(t("import.upload_hint_generic"))
                    return

                # Profile-aware hint
                upload_hint_label.set_text(
                    t("import.upload_hint_mbank")
                    if f.profile == "mbank"
                    else t("import.upload_hint_generic")
                )

                # mBank metadata banner
                if f.profile == "mbank" and f.metadata is not None:
                    meta_grid.clear()
                    with meta_grid:
                        for label, value in [
                            (t("import.detected_client"), f.metadata.client_name),
                            (t("import.detected_account_type"), f.metadata.account_type),
                            (t("import.detected_currency"), f.metadata.currency),
                            (t("import.detected_account"), f.metadata.account_number),
                            (
                                t("import.detected_period"),
                                f"{f.metadata.date_from} – {f.metadata.date_to}"
                                if f.metadata.date_from and f.metadata.date_to
                                else "—",
                            ),
                            (t("import.detected_tx_count"), str(len(f.parsed_rows))),
                        ]:
                            ui.label(label).classes("text-xs text-grey-6 font-medium")
                            ui.label(value).classes("text-sm")
                    meta_card.set_visibility(True)
                else:
                    meta_card.set_visibility(False)

                # Settings
                account_sel.value = f.target_account_id
                expense_cat_sel.value = f.expense_cat_id
                income_cat_sel.value = f.income_cat_id
                skip_dupes_cb.value = f.skip_duplicates
                auto_match_label.set_text("")
                _check_currency()

                # Preview
                _populate_preview(f.parsed_rows)

                settings_card.set_visibility(f.status in {"ready", "done"})
                preview_card.set_visibility(f.status in {"ready", "done"})
                transfer_card.set_visibility(f.profile == "generic" and f.status == "ready")

            def _populate_preview(rows: list[ParsedRow]) -> None:
                n_income = 0
                n_expense = 0
                n_transfer = 0
                for r in rows:
                    if _is_transfer_row(r):
                        n_transfer += 1
                    elif r.amount >= 0:
                        n_income += 1
                    else:
                        n_expense += 1

                stats_row.clear()
                with stats_row:
                    expense_label = t("import.stats_expense")
                    income_label = t("import.stats_income")
                    transfer_label = t("import.stats_transfer")
                    ui.chip(f"\U0001f4e5 {expense_label}: {n_expense}", color="red-2")
                    ui.chip(f"\U0001f4e4 {income_label}: {n_income}", color="green-2")
                    ui.chip(f"\U0001f504 {transfer_label}: {n_transfer}", color="blue-2")

                preview_table.rows = [
                    {
                        "idx": i,
                        "date": str(r.date),
                        "amount": f"{'+' if r.amount >= 0 else ''}{r.amount:,.2f}",
                        "description": r.description[:70],
                        "type": (
                            "transfer"
                            if _is_transfer_row(r)
                            else ("income" if r.amount >= 0 else "expense")
                        ),
                    }
                    for i, r in enumerate(rows[:20])
                ]

            def _render_queue() -> None:
                queue_container.clear()
                with queue_container:
                    if not state["queue"]:
                        ui.label(t("import.queue_empty")).classes("text-sm text-grey-6 py-2")
                        return
                    for f in state["queue"]:
                        _render_queue_row(f)

            def _render_queue_row(f: QueuedFile) -> None:
                is_active = f.id == state["active_id"]
                # Theme-aware highlight: left border + subtle ring on active.
                # Works in both light and dark themes without washing out text.
                classes = (
                    "w-full items-center gap-3 p-2 rounded cursor-pointer border-l-4 "
                    + ("border-primary" if is_active else "border-transparent")
                )
                with ui.row().classes(classes).on(
                    "click", lambda _e, fid=f.id: _set_active(fid)
                ):
                    colour = _STATUS_COLOR.get(f.status, "grey-6")
                    ui.icon(
                        "check_circle"
                        if f.status == "done"
                        else "error"
                        if f.status == "failed"
                        else "hourglass_empty"
                        if f.status == "importing"
                        else "description",
                        size="1.2rem",
                    ).classes(f"text-{colour}")
                    with ui.column().classes("flex-1 gap-0"):
                        ui.label(f.filename).classes("text-sm font-medium")
                        _queue_row_subtitle(f)
                    ui.chip(t(f"import.queue_status_{f.status}"), color=colour).props(
                        "dense outline"
                    )
                    ui.button(
                        icon="close",
                        on_click=lambda _e, fid=f.id: _remove_file(fid),
                    ).props("flat dense round color=grey-7").tooltip(t("import.queue_remove"))

            def _queue_row_subtitle(f: QueuedFile) -> None:
                parts: list[str] = []
                if f.status == "done":
                    parts.append(
                        t("import.done", count=f.imported_count)
                    )
                    if f.skipped_dupes:
                        parts.append(t("import.skipped_dupes", count=f.skipped_dupes))
                elif f.status == "failed":
                    parts.append(f.status_msg or t("import.queue_status_failed"))
                elif f.parsed_rows:
                    parts.append(t("import.rows_loaded", count=len(f.parsed_rows)))
                elif f.status_msg:
                    parts.append(f.status_msg)
                if parts:
                    ui.label(" · ".join(parts)).classes("text-xs text-grey-6")

            def _set_active(file_id: str) -> None:
                state["active_id"] = file_id
                _repaint_active()
                _render_queue()

            def _remove_file(file_id: str) -> None:
                state["queue"] = [q for q in state["queue"] if q.id != file_id]
                if state["active_id"] == file_id:
                    state["active_id"] = (
                        state["queue"][0].id if state["queue"] else None
                    )
                _render_queue()
                _repaint_active()

            # ── Upload handler ────────────────────────────────────────────────

            async def handle_upload(e: events.UploadEventArguments) -> None:
                content = _auto_decode(await e.file.read())
                f = QueuedFile(
                    id=str(uuid.uuid4()),
                    filename=e.file.name,
                    content=content,
                )
                await _parse_file(f)
                state["queue"].append(f)

                if f.status == "ready":
                    inherited = _inherit_settings(f)
                    if f.profile == "mbank":
                        auto = await _auto_match_account(f)
                        if auto:
                            inherited = True
                    if inherited:
                        ui.notify(t("import.queue_inherited"), type="info")

                # Focus the newly added file
                state["active_id"] = f.id
                _render_queue()
                _repaint_active()

            upload_widget.on_upload(handle_upload)

            # ── Import handler ────────────────────────────────────────────────

            def _validate_file(f: QueuedFile) -> str | None:
                if f.status != "ready":
                    return None  # skip silently; not eligible
                if f.target_account_id is None:
                    return t("import.select_account_hint")
                if f.expense_cat_id is None:
                    return t("import.select_expense_cat_hint")
                if f.income_cat_id is None:
                    return t("import.select_income_cat_hint")
                if f.profile == "mbank" and f.metadata and f.metadata.currency:
                    acc = next(
                        (a for a in accounts if a.id == f.target_account_id), None
                    )
                    if acc and acc.currency.upper() != f.metadata.currency.upper():
                        return t(
                            "import.currency_mismatch_block",
                            file=f.metadata.currency,
                            account=acc.currency,
                        )
                return None

            async def _import_one(f: QueuedFile) -> None:
                f.status = "importing"
                f.status_msg = ""
                _render_queue()

                error = _validate_file(f)
                if error is not None:
                    f.status = "failed"
                    f.status_msg = error
                    return

                # _validate_file guaranteed these are set when status == "ready".
                assert f.target_account_id is not None
                assert f.expense_cat_id is not None
                assert f.income_cat_id is not None
                target_account_id = f.target_account_id
                expense_cat_id = f.expense_cat_id
                income_cat_id = f.income_cat_id

                try:
                    async with AsyncSessionFactory() as session:
                        svc_import = ImportService(session)
                        if f.profile == "mbank":
                            known_digits: set[str] = {
                                re.sub(r"\D", "", a.external_account_number)
                                for a in accounts
                                if a.external_account_number
                            }
                            creates = await svc_import.to_transaction_creates_with_payees(
                                f.parsed_rows,
                                account_id=target_account_id,
                                default_expense_category_id=expense_cat_id,
                                default_income_category_id=income_cat_id,
                                known_account_digits=known_digits,
                            )
                        else:
                            creates = svc_import.to_transaction_creates(
                                f.parsed_rows,
                                account_id=target_account_id,
                                default_expense_category_id=expense_cat_id,
                                default_income_category_id=income_cat_id,
                            )

                        skipped = 0
                        if f.skip_duplicates:
                            creates, skipped = await svc_import.filter_duplicates(creates)

                        count = await TransactionService(session).create_bulk(creates)

                        if f.profile == "mbank" and f.metadata and f.metadata.account_number_digits:
                            await AccountService(session).save_external_number(
                                target_account_id, f.metadata.account_number_digits
                            )
                except Exception as exc:  # noqa: BLE001
                    f.status = "failed"
                    f.status_msg = str(exc)
                    return

                f.imported_count = count
                f.skipped_dupes = skipped
                f.status = "done"
                f.status_msg = t("import.done", count=count)

            async def do_import_all() -> None:
                eligible = [f for f in state["queue"] if f.status == "ready"]
                if not eligible:
                    ui.notify(t("import.no_files_to_import"), type="warning")
                    return

                import_all_btn.props("disable")
                try:
                    for f in eligible:
                        await _import_one(f)
                        _render_queue()
                        _repaint_active()
                finally:
                    import_all_btn.props(remove="disable")

                _render_summary()
                summary_card.set_visibility(True)

            def _render_summary() -> None:
                summary_container.clear()
                total_imp = 0
                total_skip = 0
                total_fail = 0
                with summary_container:
                    for f in state["queue"]:
                        if f.status == "done":
                            total_imp += f.imported_count
                            total_skip += f.skipped_dupes
                            ui.label(
                                t(
                                    "import.summary_row",
                                    filename=f.filename,
                                    imported=f.imported_count,
                                    skipped=f.skipped_dupes,
                                )
                            ).classes("text-sm")
                        elif f.status == "failed":
                            total_fail += 1
                            ui.label(
                                t(
                                    "import.summary_row_failed",
                                    filename=f.filename,
                                    error=f.status_msg or t("import.queue_status_failed"),
                                )
                            ).classes("text-sm text-red-600")
                summary_totals.set_text(
                    t(
                        "import.summary_totals",
                        imported=total_imp,
                        skipped=total_skip,
                        failed=total_fail,
                    )
                )

            import_all_btn.on("click", do_import_all)

            # ── Initial paint ─────────────────────────────────────────────────
            _render_queue()
            _repaint_active()
