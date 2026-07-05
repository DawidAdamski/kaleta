# SPDX-License-Identifier: AGPL-3.0-or-later
"""Import page — routing, layout, and section wiring."""

from __future__ import annotations

import uuid
from typing import Any

from nicegui import events, ui

from kaleta.i18n import t
from kaleta.services import AccountService, CategoryService, TransactionService, with_session
from kaleta.services.import_service import (
    ImportReadinessCheck,
    ImportService,
    auto_decode,
    build_known_account_digits,
    inherit_queue_settings,
    validate_import_readiness,
)
from kaleta.views.import_view.metadata_section import build_metadata_section
from kaleta.views.import_view.preview_section import build_preview_section
from kaleta.views.import_view.profile_section import build_profile_section
from kaleta.views.import_view.queue_section import build_queue_section
from kaleta.views.import_view.settings_section import build_settings_section
from kaleta.views.import_view.state import (
    QueuedFile,
    apply_settings_snapshot,
    settings_snapshot,
)
from kaleta.views.import_view.step_indicator import render_step_indicator
from kaleta.views.import_view.summary_section import build_summary_section
from kaleta.views.import_view.transfer_section import build_transfer_section
from kaleta.views.import_view.upload_section import build_upload_section
from kaleta.views.layout import page_layout


async def import_page() -> None:
    async def _load_reference(session: Any) -> tuple[Any, Any]:
        accounts = await AccountService(session).list()
        categories = await CategoryService(session).list()
        return accounts, categories

    accounts, categories = await with_session(_load_reference)

    account_options = {a.id: f"{a.name} ({a.currency})" for a in accounts}
    expense_cat_opts = CategoryService.build_option_labels(
        [c for c in categories if c.type.value == "expense"]
    )
    income_cat_opts = CategoryService.build_option_labels(
        [c for c in categories if c.type.value == "income"]
    )
    known_digits = build_known_account_digits(a.external_account_number for a in accounts)

    state: dict[str, Any] = {"queue": [], "active_id": None}

    def _active() -> QueuedFile | None:
        active_id = state["active_id"]
        if active_id is None:
            return None
        return next((f for f in state["queue"] if f.id == active_id), None)

    def _queue_snapshots() -> list[Any]:
        return [settings_snapshot(f) for f in state["queue"]]

    async def _parse_file(queued_file: QueuedFile) -> None:
        queued_file.parsed_rows = []
        queued_file.parse_errors = []
        queued_file.metadata = None
        queued_file.status_msg = ""

        async def _run_parse(session: Any) -> Any:
            svc = ImportService(session)
            return svc.parse_queued_file(queued_file.content, queued_file.profile)

        result = await with_session(_run_parse)
        queued_file.profile = result.profile
        if not result.ok:
            queued_file.status = "failed"
            queued_file.status_msg = (
                t(result.error_key, **result.error_params) if result.error_key else ""
            )
            return
        queued_file.parsed_rows = result.rows
        queued_file.parse_errors = result.errors
        queued_file.metadata = result.metadata
        queued_file.status = "ready"
        queued_file.status_msg = t("import.rows_loaded", count=len(queued_file.parsed_rows))

    def _repaint_active() -> None:
        active = _active()
        profile_section.set_active_profile(active.profile if active else None)

        if active is None:
            metadata_section.hide()
            settings_section.set_visible(False)
            preview_section.set_visible(False)
            transfer_section.set_visible(False)
            upload_section.set_hint(t("import.upload_hint_generic"))
            return

        upload_section.set_hint(
            t("import.upload_hint_mbank")
            if active.profile == "mbank"
            else t("import.upload_hint_generic")
        )

        if active.profile == "mbank" and active.metadata is not None:
            metadata_section.render(active.metadata, len(active.parsed_rows))
        else:
            metadata_section.hide()

        settings_section.load_file(active, accounts)
        preview_section.render(active.parsed_rows, known_digits)

        settings_section.set_visible(active.status in {"ready", "done"})
        preview_section.set_visible(active.status in {"ready", "done"})
        transfer_section.set_visible(active.profile == "generic" and active.status == "ready")

    def _render_queue() -> None:
        queue_section.render(
            state["queue"],
            state["active_id"],
            on_select=_set_active,
            on_remove=_remove_file,
        )

    def _set_active(file_id: str) -> None:
        state["active_id"] = file_id
        _repaint_active()
        _render_queue()

    def _remove_file(file_id: str) -> None:
        state["queue"] = [q for q in state["queue"] if q.id != file_id]
        if state["active_id"] == file_id:
            state["active_id"] = state["queue"][0].id if state["queue"] else None
        _render_queue()
        _repaint_active()

    async def _select_profile(key: str) -> None:
        active = _active()
        if active is None:
            return
        active.profile = key
        await _parse_file(active)
        _repaint_active()
        _render_queue()

    async def _auto_match_account(queued_file: QueuedFile) -> bool:
        if queued_file.profile != "mbank" or not queued_file.metadata:
            return False
        digits = queued_file.metadata.account_number_digits
        if not digits:
            return False

        async def _match(session: Any) -> Any:
            return await AccountService(session).find_by_external_number(digits[-10:])

        matched = await with_session(_match)
        if matched and matched.id in account_options:
            queued_file.target_account_id = matched.id
            return True
        return False

    async def handle_upload(e: events.UploadEventArguments) -> None:
        content = auto_decode(await e.file.read())
        queued_file = QueuedFile(
            id=str(uuid.uuid4()),
            filename=e.file.name,
            content=content,
        )
        await _parse_file(queued_file)
        state["queue"].append(queued_file)

        if queued_file.status == "ready":
            snapshot = settings_snapshot(queued_file)
            inherited = inherit_queue_settings(snapshot, _queue_snapshots())
            if inherited:
                apply_settings_snapshot(queued_file, snapshot)
            if queued_file.profile == "mbank":
                auto = await _auto_match_account(queued_file)
                if auto:
                    inherited = True
            if inherited:
                ui.notify(t("import.queue_inherited"), type="info")

        state["active_id"] = queued_file.id
        _render_queue()
        _repaint_active()

    def _on_settings_change() -> None:
        active = _active()
        if active is None:
            return
        settings_section.sync_from_widgets(active)
        settings_section.update_currency_warning(active, accounts)

    async def _import_one(queued_file: QueuedFile) -> None:
        queued_file.status = "importing"
        queued_file.status_msg = ""
        _render_queue()

        account = next((a for a in accounts if a.id == queued_file.target_account_id), None)
        error_key, error_params = validate_import_readiness(
            ImportReadinessCheck(
                target_account_id=queued_file.target_account_id,
                expense_cat_id=queued_file.expense_cat_id,
                income_cat_id=queued_file.income_cat_id,
                profile=queued_file.profile,
                metadata=queued_file.metadata,
                account_currency=account.currency if account else None,
            )
        )
        if error_key is not None:
            queued_file.status = "failed"
            queued_file.status_msg = t(error_key, **error_params)
            return

        assert queued_file.target_account_id is not None
        assert queued_file.expense_cat_id is not None
        assert queued_file.income_cat_id is not None
        target_account_id = queued_file.target_account_id
        expense_cat_id = queued_file.expense_cat_id
        income_cat_id = queued_file.income_cat_id

        try:

            async def _persist(session: Any) -> tuple[int, int]:
                svc_import = ImportService(session)
                if queued_file.profile == "mbank":
                    creates = await svc_import.to_transaction_creates_with_payees(
                        queued_file.parsed_rows,
                        account_id=target_account_id,
                        default_expense_category_id=expense_cat_id,
                        default_income_category_id=income_cat_id,
                        known_account_digits=known_digits,
                    )
                else:
                    creates = svc_import.to_transaction_creates(
                        queued_file.parsed_rows,
                        account_id=target_account_id,
                        default_expense_category_id=expense_cat_id,
                        default_income_category_id=income_cat_id,
                    )

                skipped = 0
                if queued_file.skip_duplicates:
                    creates, skipped = await svc_import.filter_duplicates(creates)

                count = await TransactionService(session).create_bulk(creates)

                if (
                    queued_file.profile == "mbank"
                    and queued_file.metadata
                    and queued_file.metadata.account_number_digits
                ):
                    await AccountService(session).save_external_number(
                        target_account_id,
                        queued_file.metadata.account_number_digits,
                    )
                return count, skipped

            count, skipped = await with_session(_persist)
        except Exception as exc:  # noqa: BLE001
            queued_file.status = "failed"
            queued_file.status_msg = str(exc)
            return

        queued_file.imported_count = count
        queued_file.skipped_dupes = skipped
        queued_file.status = "done"
        queued_file.status_msg = t("import.done", count=count)

    async def do_import_all() -> None:
        eligible = [f for f in state["queue"] if f.status == "ready"]
        if not eligible:
            ui.notify(t("import.no_files_to_import"), type="warning")
            return

        queue_section.import_all_btn.props("disable")
        try:
            for queued_file in eligible:
                await _import_one(queued_file)
                _render_queue()
                _repaint_active()
        finally:
            queue_section.import_all_btn.props(remove="disable")

        summary_section.render(state["queue"])
        summary_section.show()

    async def run_detect() -> None:
        async def _detect(session: Any) -> int:
            return await ImportService(session).detect_and_link_transfers()

        pairs = await with_session(_detect)
        msg = t("import.linked_pairs", count=pairs)
        transfer_section.set_result(msg)
        ui.notify(msg, type="positive")

    with page_layout(t("import.title")):
        ui.label(t("import.title")).classes("text-2xl font-bold")
        render_step_indicator()

        profile_section = build_profile_section(_select_profile)
        upload_section = build_upload_section()
        queue_section = build_queue_section()
        metadata_section = build_metadata_section()
        settings_section = build_settings_section(
            account_options,
            expense_cat_opts,
            income_cat_opts,
        )
        preview_section = build_preview_section()
        transfer_section = build_transfer_section(run_detect)
        summary_section = build_summary_section()

        settings_section.bind(
            on_account_change=_on_settings_change,
            on_expense_change=_on_settings_change,
            on_income_change=_on_settings_change,
            on_skip_change=_on_settings_change,
        )
        upload_section.upload_widget.on_upload(handle_upload)
        queue_section.import_all_btn.on("click", do_import_all)

        _render_queue()
        _repaint_active()
