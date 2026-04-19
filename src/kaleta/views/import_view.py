"""Unified import view — generic CSV and bank-specific profiles in one page."""

from __future__ import annotations

import re
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
            result[child.id] = f"{root.name} \u2192 {child.name}"
    return result


# ── Bank profiles ─────────────────────────────────────────────────────────────
# Each entry: (profile_key, label_i18n_key, icon, enabled)
# Add new banks here when supported.
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


def register() -> None:
    @ui.page("/import")
    async def import_page() -> None:
        async with AsyncSessionFactory() as session:
            accounts = await AccountService(session).list()
            categories = await CategoryService(session).list()

        account_options = {a.id: f"{a.name} ({a.currency})" for a in accounts}
        expense_cat_opts = _build_cat_opts([c for c in categories if c.type.value == "expense"])
        income_cat_opts = _build_cat_opts([c for c in categories if c.type.value == "income"])

        # ── Mutable state ──────────────────────────────────────────────────────
        state: dict[str, Any] = {
            "profile": "generic",
            "parsed_rows": [],  # list[ParsedRow]
            "metadata": None,  # MBankFileMetadata | None
        }

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
            # SECTION 1 — Profile selector
            # ══════════════════════════════════════════════════════════════════
            with ui.card().classes("w-full"):
                ui.label(t("import.profile_label")).classes(
                    "text-sm text-grey-6 font-medium uppercase tracking-wide mb-3"
                )
                with ui.row().classes("gap-3 flex-wrap"):
                    profile_btns: dict[str, ui.button] = {}

                    def _select_profile(key: str) -> None:
                        state["profile"] = key
                        state["parsed_rows"] = []
                        state["metadata"] = None
                        _reset_ui()
                        for k, btn in profile_btns.items():
                            btn.props(
                                "color=primary unelevated" if k == key else "color=grey-4 flat"
                            )

                    for profile_key, label_key, icon, enabled in _PROFILES:
                        is_active = profile_key == "generic"
                        btn = ui.button(
                            t(label_key),
                            icon=icon,
                            on_click=lambda k=profile_key: _select_profile(k),
                        ).props("color=primary unelevated" if is_active else "color=grey-4 flat")
                        if not enabled:
                            btn.props("disable")
                            btn.tooltip(t("import.profile_coming_soon"))
                        profile_btns[profile_key] = btn

            # ══════════════════════════════════════════════════════════════════
            # SECTION 2 — Upload
            # ══════════════════════════════════════════════════════════════════
            with ui.card().classes("w-full"):
                ui.label(t("import.upload_section")).classes("text-lg font-semibold mb-1")
                upload_hint_label = ui.label(t("import.upload_hint_generic")).classes(
                    "text-sm text-grey-6 mb-3"
                )

                file_error = ui.label("").classes("text-sm text-red-600")
                file_status = ui.label("").classes("text-sm text-green-700")

                # mBank metadata banner — hidden until mBank file is loaded
                meta_card = ui.card().classes("k-info-banner w-full bg-blue-50")
                meta_card.set_visibility(False)
                with meta_card:
                    meta_grid = ui.grid(columns=2).classes("w-full gap-x-6 gap-y-1")

                upload_widget = (
                    ui.upload(
                        label=t("import.drop_hint_generic"),
                        auto_upload=True,
                        max_files=1,
                    )
                    .props("accept=.csv flat bordered")
                    .classes("w-full mt-2")
                )

            # ══════════════════════════════════════════════════════════════════
            # SECTION 3 — Settings (shown after upload)
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
                    if account_options:
                        account_sel.value = next(iter(account_options))

                    expense_cat_sel = ui.select(
                        expense_cat_opts, label=t("import.default_expense_cat")
                    ).classes("flex-1 min-w-48")
                    income_cat_sel = ui.select(
                        income_cat_opts, label=t("import.default_income_cat")
                    ).classes("flex-1 min-w-48")

                skip_dupes_cb = ui.checkbox(t("import.skip_duplicates"), value=True)

                def _check_currency(_e: object = None) -> None:
                    metadata: MBankFileMetadata | None = state.get("metadata")
                    if not metadata:
                        return
                    acc = next((a for a in accounts if a.id == account_sel.value), None)
                    if acc and acc.currency.upper() != metadata.currency.upper():
                        currency_warn_label.set_text(
                            t(
                                "import.currency_mismatch",
                                file=metadata.currency,
                                account=acc.currency,
                            )
                        )
                    else:
                        currency_warn_label.set_text("")

                account_sel.on("update:model-value", _check_currency)

            # ══════════════════════════════════════════════════════════════════
            # SECTION 4 — Preview (shown after upload)
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

                import_btn = ui.button(t("import.import_btn"), icon="upload").props("color=primary")
                import_result = ui.label("").classes("text-sm mt-2")
                import_spinner = ui.spinner("dots", size="md")
                import_spinner.set_visibility(False)

            # ══════════════════════════════════════════════════════════════════
            # SECTION 5 — Detect internal transfers (generic only)
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

            # ── Helpers ───────────────────────────────────────────────────────

            def _reset_ui() -> None:
                """Reset all result sections when a new profile is selected."""
                file_error.set_text("")
                file_status.set_text("")
                meta_card.set_visibility(False)
                settings_card.set_visibility(False)
                preview_card.set_visibility(False)
                transfer_card.set_visibility(False)
                import_result.set_text("")
                preview_table.rows = []
                upload_hint_label.set_text(
                    t("import.upload_hint_mbank")
                    if state["profile"] == "mbank"
                    else t("import.upload_hint_generic")
                )

            def _is_transfer_row(r: ParsedRow) -> bool:
                """True when the counterparty account belongs to a registered account."""
                known: set[str] = {
                    re.sub(r"\D", "", a.external_account_number)
                    for a in accounts
                    if a.external_account_number
                }
                digits = re.sub(r"\D", "", r.raw.get("Numer rachunku", ""))
                return bool(digits and digits in known)

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
                    ui.chip(f"📥 {t('import.stats_expense')}: {n_expense}", color="red-2")
                    ui.chip(f"📤 {t('import.stats_income')}: {n_income}", color="green-2")
                    ui.chip(f"🔄 {t('import.stats_transfer')}: {n_transfer}", color="blue-2")

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

            # ── Upload handler ────────────────────────────────────────────────

            async def handle_upload(e: events.UploadEventArguments) -> None:
                file_error.set_text("")
                file_status.set_text("")
                meta_card.set_visibility(False)
                state["metadata"] = None

                content = _auto_decode(await e.file.read())
                profile = state["profile"]

                async with AsyncSessionFactory() as session:
                    svc = ImportService(session)

                    if profile == "mbank":
                        if not MBankPreprocessor.is_mbank_file(content):
                            file_error.set_text(t("import.not_mbank_file"))
                            return
                        data_section = MBankPreprocessor.extract_data_section(content)
                        if data_section is None:
                            file_error.set_text(t("import.no_data_section"))
                            return
                        meta = MBankPreprocessor.extract_metadata(content)
                        state["metadata"] = meta
                        result: ImportResult = svc.parse_csv(data_section, delimiter=";")

                        # Populate mBank metadata banner
                        meta_grid.clear()
                        with meta_grid:
                            for label, value in [
                                (t("import.detected_client"), meta.client_name),
                                (t("import.detected_account_type"), meta.account_type),
                                (t("import.detected_currency"), meta.currency),
                                (t("import.detected_account"), meta.account_number),
                                (
                                    t("import.detected_period"),
                                    f"{meta.date_from} – {meta.date_to}"
                                    if meta.date_from and meta.date_to
                                    else "—",
                                ),
                                (
                                    t("import.detected_tx_count"),
                                    str(len(result.rows)),
                                ),
                            ]:
                                ui.label(label).classes("text-xs text-grey-6 font-medium")
                                ui.label(value).classes("text-sm")
                        meta_card.set_visibility(True)

                        # Auto-match account
                        if meta.account_number_digits:
                            matched = await AccountService(session).find_by_external_number(
                                meta.account_number_digits[-10:]
                            )
                            if matched and matched.id in account_options:
                                account_sel.value = matched.id
                                auto_match_label.set_text(t("import.auto_matched"))
                            else:
                                auto_match_label.set_text("")
                        _check_currency()

                    else:
                        result = svc.parse_csv(content)

                state["parsed_rows"] = result.rows

                if result.errors:
                    file_error.set_text(" | ".join(result.errors[:3]))
                if not result.rows:
                    file_status.set_text(t("import.no_rows", skipped=result.skipped))
                    return

                file_status.set_text(t("import.rows_loaded", count=len(result.rows)))
                _populate_preview(result.rows)

                settings_card.set_visibility(True)
                preview_card.set_visibility(True)
                # Show transfer detect only for generic (mBank detects them during import)
                transfer_card.set_visibility(profile == "generic")

            upload_widget.on_upload(handle_upload)

            # ── Import handler ────────────────────────────────────────────────

            async def do_import() -> None:
                if not account_sel.value:
                    ui.notify(t("import.select_account_hint"), type="negative")
                    return
                if not expense_cat_sel.value:
                    ui.notify(t("import.select_expense_cat_hint"), type="negative")
                    return
                if not income_cat_sel.value:
                    ui.notify(t("import.select_income_cat_hint"), type="negative")
                    return

                # Block mBank import when file currency ≠ account currency
                if state["profile"] == "mbank":
                    metadata: MBankFileMetadata | None = state.get("metadata")
                    if metadata and metadata.currency:
                        acc = next((a for a in accounts if a.id == account_sel.value), None)
                        if acc and acc.currency.upper() != metadata.currency.upper():
                            ui.notify(
                                t(
                                    "import.currency_mismatch_block",
                                    file=metadata.currency,
                                    account=acc.currency,
                                ),
                                type="negative",
                            )
                            return

                import_spinner.set_visibility(True)
                import_btn.props("disable")
                import_result.set_text("")

                async with AsyncSessionFactory() as session:
                    svc_import = ImportService(session)
                    if state["profile"] == "mbank":
                        # Build set of known account digits for transfer detection
                        known_digits: set[str] = {
                            re.sub(r"\D", "", a.external_account_number)
                            for a in accounts
                            if a.external_account_number
                        }
                        creates = await svc_import.to_transaction_creates_with_payees(
                            state["parsed_rows"],
                            account_id=account_sel.value,
                            default_expense_category_id=expense_cat_sel.value,
                            default_income_category_id=income_cat_sel.value,
                            known_account_digits=known_digits,
                        )
                    else:
                        creates = svc_import.to_transaction_creates(
                            state["parsed_rows"],
                            account_id=account_sel.value,
                            default_expense_category_id=expense_cat_sel.value,
                            default_income_category_id=income_cat_sel.value,
                        )

                    skipped = 0
                    if skip_dupes_cb.value:
                        creates, skipped = await svc_import.filter_duplicates(creates)

                    count = await TransactionService(session).create_bulk(creates)

                    # mBank: save external account number for future auto-matching
                    file_metadata: MBankFileMetadata | None = state.get("metadata")
                    if file_metadata and file_metadata.account_number_digits:
                        await AccountService(session).save_external_number(
                            account_sel.value, file_metadata.account_number_digits
                        )

                import_spinner.set_visibility(False)
                import_btn.props(remove="disable")

                msg = t("import.done", count=count)
                if skipped:
                    msg += f" {t('import.skipped_dupes', count=skipped)}"
                import_result.set_text(msg)
                ui.notify(msg, type="positive")

            import_btn.on("click", do_import)
