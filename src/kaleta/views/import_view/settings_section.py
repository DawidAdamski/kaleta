# SPDX-License-Identifier: AGPL-3.0-or-later
"""Per-file import settings (account, categories, duplicate skip)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from nicegui import ui

from kaleta.i18n import t
from kaleta.services.import_service import currency_mismatch_warning
from kaleta.views.import_view.state import QueuedFile


@dataclass
class SettingsSection:
    card: ui.card
    account_sel: ui.select
    expense_cat_sel: ui.select
    income_cat_sel: ui.select
    skip_dupes_cb: ui.checkbox
    remember_cb: ui.checkbox
    pattern_input: ui.input
    currency_warn_label: ui.label
    _loading: bool = False

    def bind(
        self,
        *,
        on_account_change: Callable[[], None],
        on_expense_change: Callable[[], None],
        on_income_change: Callable[[], None],
        on_skip_change: Callable[[], None],
        on_remember_change: Callable[[], None],
    ) -> None:
        def _guard(handler: Callable[[], None]) -> Callable[[object], None]:
            def _wrapped(_e: object = None) -> None:
                if self._loading:
                    return
                handler()

            return _wrapped

        self.account_sel.on("update:model-value", _guard(on_account_change))
        self.expense_cat_sel.on("update:model-value", _guard(on_expense_change))
        self.income_cat_sel.on("update:model-value", _guard(on_income_change))
        self.skip_dupes_cb.on("update:model-value", _guard(on_skip_change))
        self.remember_cb.on("update:model-value", _guard(on_remember_change))
        self.pattern_input.on("update:model-value", _guard(on_remember_change))

    def load_file(self, file: QueuedFile, accounts: list[Any]) -> None:
        self._loading = True
        try:
            self.account_sel.value = file.target_account_id
            self.expense_cat_sel.value = file.expense_cat_id
            self.income_cat_sel.value = file.income_cat_id
            self.skip_dupes_cb.value = file.skip_duplicates
            self.remember_cb.value = file.remember_mapping
            self.pattern_input.value = file.filename_pattern or file.filename
            self.pattern_input.set_visibility(bool(file.remember_mapping))
            self._update_currency_warning(file, accounts)
        finally:
            self._loading = False

    def sync_from_widgets(self, file: QueuedFile) -> None:
        file.target_account_id = self.account_sel.value
        file.expense_cat_id = self.expense_cat_sel.value
        file.income_cat_id = self.income_cat_sel.value
        file.skip_duplicates = bool(self.skip_dupes_cb.value)
        file.remember_mapping = bool(self.remember_cb.value)
        file.filename_pattern = (self.pattern_input.value or "").strip()
        self.pattern_input.set_visibility(file.remember_mapping)

    def update_currency_warning(self, file: QueuedFile, accounts: list[Any]) -> None:
        self._update_currency_warning(file, accounts)

    def _update_currency_warning(self, file: QueuedFile, accounts: list[Any]) -> None:
        if file.metadata is None or file.target_account_id is None:
            self.currency_warn_label.set_text("")
            return
        account = next((a for a in accounts if a.id == file.target_account_id), None)
        if account and currency_mismatch_warning(
            file_currency=file.metadata.currency,
            account_currency=account.currency,
        ):
            self.currency_warn_label.set_text(
                t(
                    "import.currency_mismatch",
                    file=file.metadata.currency,
                    account=account.currency,
                )
            )
        else:
            self.currency_warn_label.set_text("")

    def set_visible(self, visible: bool) -> None:
        self.card.set_visibility(visible)


def build_settings_section(
    account_options: dict[int, str],
    expense_cat_opts: dict[int, str],
    income_cat_opts: dict[int, str],
) -> SettingsSection:
    card = ui.card().classes("w-full")
    card.set_visibility(False)
    with card:
        ui.label(t("import.settings_section")).classes("text-lg font-semibold mb-3")
        ui.label("").classes("text-sm text-green-700")
        currency_warn_label = ui.label("").classes("text-sm text-amber-600")
        with ui.row().classes("w-full gap-4 flex-wrap"):
            account_sel = ui.select(account_options, label=t("import.target_account")).classes(
                "flex-1 min-w-64"
            )
            expense_cat_sel = ui.select(
                expense_cat_opts, label=t("import.default_expense_cat")
            ).classes("flex-1 min-w-48")
            income_cat_sel = ui.select(
                income_cat_opts, label=t("import.default_income_cat")
            ).classes("flex-1 min-w-48")
        with ui.row().classes("items-center gap-1"):
            skip_dupes_cb = ui.checkbox(t("import.skip_duplicates"), value=True)
            ui.icon("help_outline", size="1rem").classes("text-slate-500 cursor-help").tooltip(
                t("import.skip_duplicates_help")
            )
        with ui.column().classes("w-full gap-1 mt-2"):
            remember_cb = ui.checkbox(t("import.remember_mapping"), value=True)
            ui.label(t("import.remember_mapping_hint")).classes("text-xs text-slate-500")
            pattern_input = ui.input(t("import.filename_pattern")).classes("w-full max-w-md")
    return SettingsSection(
        card=card,
        account_sel=account_sel,
        expense_cat_sel=expense_cat_sel,
        income_cat_sel=income_cat_sel,
        skip_dupes_cb=skip_dupes_cb,
        remember_cb=remember_cb,
        pattern_input=pattern_input,
        currency_warn_label=currency_warn_label,
    )
