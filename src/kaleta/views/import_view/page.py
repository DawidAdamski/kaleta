# SPDX-License-Identifier: AGPL-3.0-or-later
"""Import page — routing, layout, and section wiring."""

from __future__ import annotations

import uuid
from typing import Any

from nicegui import events, ui

from kaleta.i18n import t
from kaleta.services import (
    AccountService,
    CategoryService,
    ImportRuleService,
    TransactionService,
    with_session,
)
from kaleta.services.import_service import (
    ColumnMapping,
    ImportReadinessCheck,
    ImportService,
    auto_decode,
    build_known_account_digits,
    inherit_queue_settings,
    validate_import_readiness,
)
from kaleta.views.import_view.coverage_section import build_coverage_section
from kaleta.views.import_view.mapping_section import build_mapping_section
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
    async def _load_reference(session: Any) -> tuple[Any, Any, Any, Any]:
        accounts = await AccountService(session).list()
        categories = await CategoryService(session).list()
        activity = await AccountService(session).list_with_activity()
        runs = await ImportService(session).list_recent_runs(limit=20)
        return accounts, categories, activity, runs

    accounts, categories, activity_rows, recent_runs = await with_session(_load_reference)

    account_options = {a.id: f"{a.name} ({a.currency})" for a in accounts}
    account_names = {a.id: a.name for a in accounts}
    expense_cat_opts = CategoryService.build_option_labels(
        [c for c in categories if c.type.value == "expense"]
    )
    income_cat_opts = CategoryService.build_option_labels(
        [c for c in categories if c.type.value == "income"]
    )
    known_digits = build_known_account_digits(a.external_account_number for a in accounts)

    def _history_tuples(runs: list[Any]) -> list[tuple[str, str, str, int, int]]:
        rows: list[tuple[str, str, str, int, int]] = []
        for run in runs:
            when = run.created_at.isoformat()[:16].replace("T", " ") if run.created_at else "—"
            account_name = (
                run.account.name
                if getattr(run, "account", None) is not None
                else account_names.get(run.account_id, str(run.account_id))
            )
            rows.append((when, run.filename, account_name, run.imported_count, run.skipped_count))
        return rows

    state: dict[str, Any] = {
        "queue": [],
        "active_id": None,
        "last_settings": None,
        "bulk_account_id": None,
        "activity_rows": activity_rows,
        "history_rows": _history_tuples(recent_runs),
    }

    def _active() -> QueuedFile | None:
        active_id = state["active_id"]
        if active_id is None:
            return None
        return next((f for f in state["queue"] if f.id == active_id), None)

    def _inheritance_priors(current_id: str) -> list[Any]:
        priors = [settings_snapshot(f) for f in state["queue"] if f.id != current_id]
        if not priors and state["last_settings"] is not None:
            return [state["last_settings"]]
        return priors

    async def _parse_file(queued_file: QueuedFile) -> None:
        queued_file.parsed_rows = []
        queued_file.parse_errors = []
        queued_file.metadata = None
        queued_file.status_msg = ""
        mapping = queued_file.column_mapping

        async def _run_parse(session: Any) -> Any:
            svc = ImportService(session)
            return svc.parse_queued_file(
                queued_file.content,
                queued_file.profile,
                mapping=mapping,
            )

        result = await with_session(_run_parse)
        queued_file.profile = result.profile
        queued_file.inspection = result.inspection
        if result.column_mapping is not None:
            queued_file.column_mapping = result.column_mapping
        queued_file.parse_errors = list(result.errors)

        if result.ok:
            queued_file.parsed_rows = result.rows
            queued_file.metadata = result.metadata
            queued_file.status = "ready"
            queued_file.status_msg = t("import.rows_loaded", count=len(queued_file.parsed_rows))
            return

        if result.needs_mapping:
            queued_file.parsed_rows = result.rows
            queued_file.metadata = result.metadata
            queued_file.status = "needs_mapping"
            if result.error_key:
                queued_file.status_msg = t(result.error_key, **result.error_params)
            else:
                queued_file.status_msg = t("import.mapping_required")
            return

        queued_file.status = "failed"
        queued_file.status_msg = (
            t(result.error_key, **result.error_params) if result.error_key else ""
        )

    def _repaint_active() -> None:
        active = _active()
        profile_section.set_active_profile(active.profile if active else None)

        if active is None:
            metadata_section.hide()
            mapping_section.set_visible(False)
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

        show_mapping = active.profile == "generic" and active.status in {
            "ready",
            "needs_mapping",
            "done",
        }
        if show_mapping:
            mapping_section.load_file(active)
        mapping_section.set_visible(show_mapping)

        settings_section.load_file(active, accounts)
        preview_section.render(active.parsed_rows, known_digits)

        show_settings = active.status in {"ready", "done"}
        settings_section.set_visible(show_settings)
        preview_section.set_visible(active.status in {"ready", "done", "needs_mapping"})
        transfer_section.set_visible(active.profile == "generic" and active.status == "ready")

    def _render_queue() -> None:
        queue_section.render(
            state["queue"],
            state["active_id"],
            on_select=_set_active,
            on_remove=_remove_file,
        )

    def _set_active(file_id: str) -> None:
        previous = _active()
        if previous is not None and previous.id != file_id and not settings_section._loading:
            settings_section.sync_from_widgets(previous)
        state["active_id"] = file_id
        _repaint_active()
        _render_queue()

    def _remove_file(file_id: str) -> None:
        state["queue"] = [q for q in state["queue"] if q.id != file_id]
        if state["active_id"] == file_id:
            state["active_id"] = state["queue"][0].id if state["queue"] else None
        _render_queue()
        _repaint_active()

    def _start_new_import() -> None:
        if state["queue"]:
            state["last_settings"] = settings_snapshot(state["queue"][-1])
        state["queue"] = []
        state["active_id"] = None
        summary_section.hide()
        upload_section.upload_widget.reset()
        _render_queue()
        _repaint_active()

    async def _select_profile(key: str) -> None:
        active = _active()
        if active is None:
            return
        active.profile = key
        if key == "mbank":
            active.column_mapping = None
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

    async def _apply_import_rule(queued_file: QueuedFile) -> bool:
        async def _match(session: Any) -> Any:
            return await ImportRuleService(session).match(queued_file.filename)

        rule = await with_session(_match)
        if rule is None:
            return False
        queued_file.matched_rule_id = rule.id
        queued_file.matched_rule_pattern = rule.filename_pattern
        queued_file.filename_pattern = rule.filename_pattern
        if rule.account_id in account_options:
            queued_file.target_account_id = rule.account_id
        mapping = ColumnMapping.from_dict(dict(rule.column_mapping or {}))
        if mapping.is_complete() or any(
            getattr(mapping, field) is not None
            for field in ("date", "amount", "description", "payee", "debit", "credit")
        ):
            queued_file.column_mapping = mapping
        if rule.delimiter and queued_file.inspection is None:
            # Delimiter is re-detected on parse; stored for future use.
            pass
        return True

    def _apply_bulk_default(queued_file: QueuedFile) -> bool:
        bulk_id = state["bulk_account_id"]
        if bulk_id is None or queued_file.matched_rule_id is not None:
            return False
        if queued_file.target_account_id is not None:
            return False
        if bulk_id not in account_options:
            return False
        queued_file.target_account_id = bulk_id
        queued_file.from_bulk_default = True
        return True

    async def handle_upload(e: events.UploadEventArguments) -> None:
        content = auto_decode(await e.file.read())
        suggested = ImportRuleService.suggest_filename_pattern(e.file.name)
        queued_file = QueuedFile(
            id=str(uuid.uuid4()),
            filename=e.file.name,
            content=content,
            filename_pattern=suggested,
        )

        rule_applied = await _apply_import_rule(queued_file)

        # Inherit settings (including column mapping) before the first parse,
        # but never overwrite fields already filled from a matched rule.
        snapshot = settings_snapshot(queued_file)
        inherited = inherit_queue_settings(snapshot, _inheritance_priors(queued_file.id))
        if inherited:
            if queued_file.target_account_id is not None:
                snapshot.target_account_id = queued_file.target_account_id
            if queued_file.column_mapping is not None:
                snapshot.column_mapping = queued_file.column_mapping
            apply_settings_snapshot(queued_file, snapshot)

        bulk_applied = _apply_bulk_default(queued_file)

        await _parse_file(queued_file)
        state["queue"].append(queued_file)

        if rule_applied:
            ui.notify(
                t("import.rule_applied", pattern=queued_file.matched_rule_pattern or ""),
                type="info",
            )
        elif queued_file.status in {"ready", "needs_mapping"} and inherited:
            ui.notify(t("import.queue_inherited"), type="info")
        elif bulk_applied:
            ui.notify(t("import.bulk_applied"), type="info")

        if queued_file.status == "ready" and queued_file.profile == "mbank":
            auto = await _auto_match_account(queued_file)
            if auto and not rule_applied:
                ui.notify(t("import.queue_inherited"), type="info")

        state["active_id"] = queued_file.id
        summary_section.hide()
        _render_queue()
        _repaint_active()

    def _on_settings_change() -> None:
        if settings_section._loading:
            return
        active = _active()
        if active is None:
            return
        settings_section.sync_from_widgets(active)
        active.from_bulk_default = False
        settings_section.update_currency_warning(active, accounts)

    async def _on_mapping_change() -> None:
        active = _active()
        if active is None or active.profile != "generic":
            return
        mapping_section.sync_to_file(active)
        await _parse_file(active)
        _repaint_active()
        _render_queue()

    async def _save_remembered_rule(queued_file: QueuedFile) -> None:
        if not queued_file.remember_mapping:
            return
        if queued_file.target_account_id is None:
            return
        mapping = queued_file.column_mapping
        mapping_dict = mapping.to_dict() if mapping is not None else {}
        delimiter = queued_file.inspection.delimiter if queued_file.inspection else None

        async def _upsert(session: Any) -> None:
            svc = ImportRuleService(session)
            rule = await svc.upsert_from_import(
                filename=queued_file.filename,
                filename_pattern=queued_file.filename_pattern or None,
                account_id=queued_file.target_account_id,  # type: ignore[arg-type]
                column_mapping=mapping_dict,
                delimiter=delimiter,
            )
            queued_file.matched_rule_id = rule.id
            queued_file.matched_rule_pattern = rule.filename_pattern

        await with_session(_upsert)

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

            async def _persist(session: Any) -> tuple[int, list[Any]]:
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

                skipped_rows: list[Any] = []
                if queued_file.skip_duplicates:
                    creates, skipped_rows = await svc_import.filter_duplicates(creates)

                creates = await svc_import.apply_categorisation_rules(creates)
                dates = [c.date for c in creates]
                svc_import.record_import_run(
                    account_id=target_account_id,
                    filename=queued_file.filename,
                    profile=queued_file.profile,
                    imported_count=len(creates),
                    skipped_count=len(skipped_rows),
                    row_date_min=min(dates) if dates else None,
                    row_date_max=max(dates) if dates else None,
                )
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
                return count, skipped_rows

            count, skipped_rows = await with_session(_persist)
        except Exception as exc:  # noqa: BLE001
            queued_file.status = "failed"
            queued_file.status_msg = str(exc)
            return

        queued_file.imported_count = count
        queued_file.skipped_rows = skipped_rows
        queued_file.skipped_dupes = len(skipped_rows)
        queued_file.status = "done"
        queued_file.status_msg = t("import.done", count=count)

        try:
            await _save_remembered_rule(queued_file)
            rule_id = queued_file.matched_rule_id
            if rule_id is not None:

                async def _touch(session: Any, rid: int = rule_id) -> None:
                    await ImportRuleService(session).touch_last_used(rid)

                await with_session(_touch)
        except Exception as exc:  # noqa: BLE001
            ui.notify(t("import.rule_save_failed", error=str(exc)), type="warning")

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
            ready = sum(1 for f in state["queue"] if f.status == "ready")
            queue_section.update_import_button(ready)

        if state["queue"]:
            state["last_settings"] = settings_snapshot(state["queue"][-1])
        summary_section.render(state["queue"])
        summary_section.show()
        await _refresh_coverage()

    async def _refresh_coverage() -> None:
        async def _load(session: Any) -> tuple[Any, Any]:
            activity = await AccountService(session).list_with_activity()
            runs = await ImportService(session).list_recent_runs(limit=20)
            return activity, runs

        activity, runs = await with_session(_load)
        state["activity_rows"] = activity
        state["history_rows"] = _history_tuples(runs)
        coverage_section.render(state["activity_rows"], recent_runs=state["history_rows"])

    async def run_detect() -> None:
        async def _detect(session: Any) -> int:
            return await ImportService(session).detect_and_link_transfers()

        pairs = await with_session(_detect)
        msg = t("import.linked_pairs", count=pairs)
        transfer_section.set_result(msg)
        ui.notify(msg, type="positive")

    def _on_bulk_account_change(_e: object = None) -> None:
        value = queue_section.bulk_account_sel.value
        state["bulk_account_id"] = int(value) if value is not None else None
        if state["bulk_account_id"] is None:
            return
        for queued_file in state["queue"]:
            if queued_file.matched_rule_id is not None:
                continue
            if queued_file.status in {"done", "failed", "importing"}:
                continue
            if queued_file.target_account_id is None or queued_file.from_bulk_default:
                queued_file.target_account_id = state["bulk_account_id"]
                queued_file.from_bulk_default = True
        _render_queue()
        _repaint_active()

    with page_layout(t("import.title")):
        ui.label(t("import.title")).classes("text-2xl font-bold")
        render_step_indicator()

        profile_section = build_profile_section(_select_profile)
        upload_section = build_upload_section()
        coverage_section = build_coverage_section()
        coverage_section.render(state["activity_rows"], recent_runs=state["history_rows"])
        queue_section = build_queue_section(account_options)
        metadata_section = build_metadata_section()
        mapping_section = build_mapping_section()
        settings_section = build_settings_section(
            account_options,
            expense_cat_opts,
            income_cat_opts,
        )
        preview_section = build_preview_section()
        transfer_section = build_transfer_section(run_detect)
        summary_section = build_summary_section()

        mapping_section.bind(on_change=_on_mapping_change)
        settings_section.bind(
            on_account_change=_on_settings_change,
            on_expense_change=_on_settings_change,
            on_income_change=_on_settings_change,
            on_skip_change=_on_settings_change,
            on_remember_change=_on_settings_change,
        )
        queue_section.bulk_account_sel.on("update:model-value", _on_bulk_account_change)
        upload_section.upload_widget.on_upload(handle_upload)
        queue_section.import_all_btn.on("click", do_import_all)
        summary_section.bind_start_new(_start_new_import)

        _render_queue()
        _repaint_active()
