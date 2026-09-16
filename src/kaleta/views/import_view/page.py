# SPDX-License-Identifier: AGPL-3.0-or-later
"""Import page — routing, layout, and section wiring."""

from __future__ import annotations

import uuid
from typing import Any

from nicegui import events, ui

from kaleta.i18n import plural_key, t
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
    build_known_account_digits,
    decode_upload,
    inherit_queue_settings,
    validate_import_readiness,
)
from kaleta.views.import_view.constants import METADATA_PROFILES
from kaleta.views.import_view.coverage_section import build_coverage_section
from kaleta.views.import_view.mapping_section import build_mapping_section
from kaleta.views.import_view.metadata_section import build_metadata_section
from kaleta.views.import_view.preview_section import build_preview_section
from kaleta.views.import_view.profile_section import build_profile_section
from kaleta.views.import_view.queue_section import build_queue_section
from kaleta.views.import_view.settings_section import build_settings_section
from kaleta.views.import_view.state import (
    STEP_CONFIRM,
    STEP_FORMAT,
    STEP_MAPPING,
    STEP_PREVIEW,
    STEP_SETTINGS,
    STEP_UPLOAD,
    QueuedFile,
    apply_settings_snapshot,
    current_step,
    import_button_label,
    queue_is_terminal,
    settings_block_reason,
    settings_snapshot,
)
from kaleta.views.import_view.step_indicator import render_step_indicator
from kaleta.views.import_view.summary_section import build_summary_section
from kaleta.views.import_view.transfer_section import build_transfer_section
from kaleta.views.import_view.upload_section import build_upload_section
from kaleta.views.import_view.wizard import (
    STEP_LABEL_KEYS,
    can_continue,
    clamp_viewed,
    continue_blocked_reason,
    next_step,
    prev_step,
    steps_for,
)
from kaleta.views.layout import page_layout
from kaleta.views.settings.user_prefs import (
    get_import_skip_duplicates_default,
    get_transfer_amount_tolerance,
    get_transfer_pairing_days,
)
from kaleta.views.theme import BODY_MUTED, DISCLOSURE, MONO, PAGE_TITLE


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
        # The step on screen. ``current_step`` says where the *work* is; this
        # says where the reader is, which is behind it whenever they walk back.
        "step": STEP_UPLOAD,
        # True once the reader has picked a step for themselves. An upload
        # that finishes afterwards must not drag them off it — see
        # `handle_upload`.
        "step_chosen": False,
        # True while the summary of a finished run is on screen. The run's
        # own step is Confirm even when the active file failed, which its
        # `current_step` alone would answer with Upload — leaving the
        # summary of everything else on a step nobody could reach.
        "run_finished": False,
        "importing": False,
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
        queued_file.error_rows = []
        queued_file.metadata = None
        queued_file.status_msg = ""
        mapping = queued_file.column_mapping

        async def _run_parse(session: Any) -> Any:
            svc = ImportService(session)
            return svc.parse_queued_file(
                queued_file.content,
                queued_file.profile,
                mapping=mapping,
                filename=queued_file.filename,
            )

        result = await with_session(_run_parse)
        queued_file.profile = result.profile
        queued_file.inspection = result.inspection
        if result.column_mapping is not None:
            queued_file.column_mapping = result.column_mapping
            if mapping is None:
                # Nothing went in, so what came back is the importer's own
                # guess. A re-parse after the user moves a picker sends that
                # picker's value in, and must not claim it as a guess.
                queued_file.auto_mapping = result.column_mapping
        queued_file.parse_errors = list(result.errors)
        queued_file.error_rows = list(result.error_rows)

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

    def _active_account_currency() -> str | None:
        active = _active()
        if active is None or active.target_account_id is None:
            return None
        account = next((a for a in accounts if a.id == active.target_account_id), None)
        return account.currency if account else None

    def _repaint_active(*, sync: bool = True) -> None:
        """Load the active file into every section, and re-decide the step.

        Unchanged in what it does: each section still decides *whether* it
        applies to this file. What is new is the last line — the shell then
        decides which of them is in front of the reader, so an edit that
        sends the work backwards takes the reader with it. Callers that
        follow with their own ``_sync_step`` pass ``sync=False``: four
        refreshables rebuilt twice per event is four too many.
        """
        active = _active()
        profile_section.set_active_profile(active.profile if active else None)

        if active is None:
            metadata_section.hide()
            mapping_section.set_visible(False)
            settings_section.set_visible(False)
            preview_section.set_visible(False)
            transfer_section.set_visible(False)
            upload_section.set_hint(t("import.upload_hint_generic"))
            if sync:
                _sync_step()
            return

        upload_section.set_hint(
            t(f"import.upload_hint_{active.profile}")
            if active.profile in METADATA_PROFILES
            else t("import.upload_hint_generic")
        )

        if active.profile in METADATA_PROFILES and active.metadata is not None:
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
        if sync:
            _sync_step()

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
        state["run_finished"] = False
        summary_section.hide()
        upload_section.upload_widget.reset()
        _render_queue()
        # A new run is the page's to place: the reader asked for it.
        state["step_chosen"] = False
        _repaint_active(sync=False)
        _sync_step(follow=True)

    async def _select_profile(key: str) -> None:
        active = _active()
        if active is None:
            return
        active.profile = key
        if key == "mbank":
            active.column_mapping = None
            active.auto_mapping = None
        await _parse_file(active)
        _repaint_active(sync=False)
        _render_queue()
        # mbank/pko/wise have no mapping step: the one the reader is on may
        # have just stopped existing.
        _sync_step()

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
            queued_file.auto_mapping = mapping
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
        # A finished run is cleared before the new file joins the queue, so the
        # user never sees stale done-rows next to it. Checked before the first
        # await so that in a multi-file drop — one background task per file —
        # only the first task can find a terminal queue; see the plan's
        # implementation notes. Resetting the upload widget from inside its own
        # handler is safe: the POST body is fully parsed before any handler runs.
        if queue_is_terminal(state["queue"]):
            had_failed = any(f.status == "failed" for f in state["queue"])
            _start_new_import()
            if had_failed:
                ui.notify(t("import.queue_reset_failed"), type="info")

        content, encoding = decode_upload(await e.file.read())
        suggested = ImportRuleService.suggest_filename_pattern(e.file.name)
        queued_file = QueuedFile(
            id=str(uuid.uuid4()),
            filename=e.file.name,
            content=content,
            encoding=encoding,
            filename_pattern=suggested,
            skip_duplicates=get_import_skip_duplicates_default(),
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

        # A fresh file moves the reader to whatever it needs — the whole
        # point of a wizard is not having to go and find the next question.
        # But a multi-file drop runs one handler per file, and a reader who
        # walks off while the third is still parsing keeps what they were
        # looking at: dropping a file from the upload step is an invitation
        # to be taken to it, standing somewhere else is not. The file still
        # joins the queue, and the switcher on steps 3–5 still counts it.
        takes_focus = not state["step_chosen"] or state["step"] == STEP_UPLOAD
        if takes_focus or state["active_id"] is None:
            state["active_id"] = queued_file.id
        state["run_finished"] = False
        summary_section.hide()
        _render_queue()
        _repaint_active(sync=False)
        _sync_step(follow=takes_focus)

    def _on_settings_change() -> None:
        if settings_section._loading:
            return
        active = _active()
        if active is None:
            return
        settings_section.sync_from_widgets(active)
        active.from_bulk_default = False
        settings_section.update_currency_warning(active, accounts)
        # Choosing the account is what the Settings step is for, so the line
        # and the Continue button both have to move when it happens.
        _sync_step()

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
        if state["importing"]:
            # The footer draws the button disabled while a run is going, but
            # that is a websocket round trip away; a second click inside it
            # would otherwise start a second loop over the same files.
            return

        eligible = [f for f in state["queue"] if f.status == "ready"]
        if not eligible:
            ui.notify(t("import.no_files_to_import"), type="warning")
            return

        # The footer reads this rather than being poked: it is rebuilt on
        # every step change anyway, and one source for "can you press it" is
        # one place for that answer to be wrong.
        state["importing"] = True
        wizard_footer.refresh()
        try:
            for queued_file in eligible:
                await _import_one(queued_file)
                _render_queue()
                _repaint_active()
        finally:
            state["importing"] = False

        if state["queue"]:
            state["last_settings"] = settings_snapshot(state["queue"][-1])
        summary_section.render(state["queue"])
        summary_section.show()
        state["run_finished"] = True
        await _refresh_coverage()
        # Every file has finished, so the work is on Confirm; the reader goes
        # with it rather than being left on a preview of rows already in.
        state["step_chosen"] = False
        _sync_step(follow=True)

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
        pairing_days = get_transfer_pairing_days()
        amount_tolerance = get_transfer_amount_tolerance()

        async def _detect(session: Any) -> int:
            return await ImportService(session).detect_and_link_transfers(
                max_days_apart=pairing_days,
                amount_tolerance=amount_tolerance,
            )

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

    # ── The wizard shell ─────────────────────────────────────────────────
    #
    # ``current_step`` has always known which step the file is waiting on;
    # until now only the progress line acted on it, over a page showing all
    # six steps at once. These three functions are what make the page agree
    # with its own line: one panel on screen, a footer that moves, and a
    # reader who may walk back without the work moving with them.

    def _reachable() -> int:
        if state["run_finished"]:
            return STEP_CONFIRM
        return current_step(_active(), account_currency=_active_account_currency())

    def _settings_reason(active: QueuedFile | None) -> str | None:
        """The settings step's own refusal, translated."""
        if active is None:
            return None
        blocked = settings_block_reason(active, account_currency=_active_account_currency())
        return None if blocked is None else t(blocked[0], **blocked[1])

    def _sync_step(*, follow: bool = False) -> None:
        """Show the viewed step's panel and nothing else.

        ``follow`` puts the reader where the work is — what an upload or a
        finished import should do. Otherwise the reader stays put, clamped
        to a step that still exists and that the work has reached.
        """
        active = _active()
        steps = steps_for(active)
        reachable = _reachable()
        viewed = reachable if follow else clamp_viewed(state["step"], reachable, steps)
        state["step"] = viewed
        for step, panel in step_panels.items():
            panel.set_visibility(step == viewed)
        step_line.refresh()
        page_header.refresh()
        file_switcher.refresh()
        wizard_footer.refresh()

    def _goto(step: int) -> None:
        """The reader picks a step, and keeps it until the page may move."""
        state["step"] = step
        state["step_chosen"] = True
        _sync_step()

    def _go_back() -> None:
        _goto(prev_step(state["step"], steps_for(_active())))

    def _go_forward() -> None:
        _goto(next_step(state["step"], steps_for(_active())))

    def _eyebrow() -> None:
        """The file this screen is about, and how big it is (artboard 2d).

        The count is a figure, so it is set in the app's figure face and
        separator — the same call the mapping caption makes, which is the
        other place the same number appears.
        """
        active = _active()
        if active is None:
            ui.label(t("import.eyebrow_no_file"))
            return
        rows = (
            active.inspection.total_rows
            if active.inspection is not None
            else len(active.parsed_rows)
        )
        ui.label(f"{active.filename} ·")
        ui.label(t(plural_key("import.rows_count", rows), count=f"{rows:,}")).classes(MONO)

    def _select_file_at(index: int) -> None:
        queue = state["queue"]
        if 0 <= index < len(queue):
            _set_active(queue[index].id)

    with page_layout(t("import.title")):

        @ui.refreshable
        def page_header() -> None:
            with ui.column().classes("w-full gap-1"):
                with ui.row().classes("k-eyebrow items-baseline gap-1").props("data-page-eyebrow"):
                    _eyebrow()
                ui.label(t("import.title")).classes(PAGE_TITLE)

        @ui.refreshable
        def file_switcher() -> None:
            """``< File 2 of 4 >`` — the queue, on the steps that act on one file.

            The queue card itself belongs to Upload: a list of files under the
            mapping step is the scroll this wizard exists to remove. What is
            left of it here is the one thing those steps need, which is a way
            to reach the next file without going back.
            """
            queue = state["queue"]
            if state["step"] not in {STEP_MAPPING, STEP_SETTINGS, STEP_PREVIEW} or len(queue) < 2:
                return
            active = _active()
            index = next((i for i, f in enumerate(queue) if active and f.id == active.id), 0)
            with ui.row().classes("w-full items-center gap-2").props("data-file-switcher"):
                back = ui.button(icon="chevron_left", on_click=lambda: _select_file_at(index - 1))
                back.props("flat dense round color=primary")
                if index == 0:
                    back.props("disable")
                ui.label(t("import.file_n_of_m", n=index + 1, m=len(queue))).classes(BODY_MUTED)
                fwd = ui.button(icon="chevron_right", on_click=lambda: _select_file_at(index + 1))
                fwd.props("flat dense round color=primary")
                if index >= len(queue) - 1:
                    fwd.props("disable")

        @ui.refreshable
        def step_line() -> None:
            render_step_indicator(
                _reachable(),
                viewed=state["step"],
                on_step=_goto,
                steps=steps_for(_active()),
            )

        @ui.refreshable
        def wizard_footer() -> None:
            """``Back`` and ``Continue to <step>`` — or, on Preview, ``Import``.

            The import used to run from a button in the queue card's header,
            which on a six-card page was as good a place as any. On a wizard
            it belongs at the end of the last step you can still change your
            mind on, where ``Continue`` would otherwise be.
            """
            viewed = state["step"]
            active = _active()
            steps = steps_for(active)
            reachable = _reachable()
            with ui.row().classes("w-full items-center gap-3 mt-1").props("data-wizard-footer"):
                back = ui.button(t("import.back"), icon="chevron_left", on_click=_go_back)
                back.props("flat no-caps color=primary")
                if prev_step(viewed, steps) == viewed:
                    back.props("disable")
                ui.space()
                if viewed == STEP_PREVIEW:
                    ready = sum(1 for f in state["queue"] if f.status == "ready")
                    run = ui.button(
                        import_button_label(ready), icon="upload", on_click=do_import_all
                    ).props("unelevated no-caps color=primary")
                    run.props["data-import-run"] = "true"
                    if ready <= 0 or state["importing"]:
                        run.props("disable")
                    return
                reason = continue_blocked_reason(
                    active, viewed, reachable, settings_reason=_settings_reason(active)
                )
                if reason:
                    ui.label(reason).classes(BODY_MUTED).props("data-blocked-reason")
                if viewed == STEP_CONFIRM:
                    return
                nxt = next_step(viewed, steps)
                # `icon-right` is a Quasar prop taking an icon *name*, not a
                # `ui.button` argument — the same trap the top bar's chevrons
                # fell into (see `restyle-dashboard-rethink`).
                forward = ui.button(
                    t("import.continue_to", step=t(STEP_LABEL_KEYS[nxt])),
                    on_click=_go_forward,
                ).props("unelevated no-caps color=primary icon-right=chevron_right")
                forward.props["data-continue"] = "true"
                if not can_continue(viewed, reachable, steps):
                    forward.props("disable")

        page_header()
        step_line()
        file_switcher()

        step_panels: dict[int, ui.column] = {}

        def _panel(step: int) -> ui.column:
            panel = ui.column().classes("w-full gap-4").props(f'data-step-panel="{step}"')
            step_panels[step] = panel
            return panel

        with _panel(STEP_FORMAT):
            profile_section = build_profile_section(_select_profile)
            # Coverage and history are not steps — they are what you consult
            # before choosing a format, and a card each on the way to every
            # import is how the old page got long.
            # No card of its own: what it opens onto is two cards already.
            with ui.expansion(t("import.reference_panels")).classes(f"{DISCLOSURE} w-full"):
                coverage_section = build_coverage_section()
                coverage_section.render(state["activity_rows"], recent_runs=state["history_rows"])

        with _panel(STEP_UPLOAD):
            upload_section = build_upload_section()
            metadata_section = build_metadata_section()
            queue_section = build_queue_section(account_options)

        with _panel(STEP_MAPPING):
            mapping_section = build_mapping_section()

        with _panel(STEP_SETTINGS):
            settings_section = build_settings_section(
                account_options,
                expense_cat_opts,
                income_cat_opts,
            )

        with _panel(STEP_PREVIEW):
            preview_section = build_preview_section()
            transfer_section = build_transfer_section(run_detect)

        with _panel(STEP_CONFIRM):
            summary_section = build_summary_section()

        wizard_footer()

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
        summary_section.bind_start_new(_start_new_import)

        _render_queue()
        _repaint_active()
        _sync_step(follow=True)
