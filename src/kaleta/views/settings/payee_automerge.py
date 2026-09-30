# SPDX-License-Identifier: AGPL-3.0-or-later
"""Settings → Housekeeping: automatic payee merging and the on-demand merge scan."""

from __future__ import annotations

from typing import Any

from nicegui import ui

from kaleta.i18n import t
from kaleta.services import with_session
from kaleta.services.payee_merge_service import (
    AUTO_MERGE_THRESHOLD_MAX,
    AUTO_MERGE_THRESHOLD_MIN,
    MergeScanResult,
    PayeeMergeService,
)
from kaleta.views.error_handling import handle_kaleta_error
from kaleta.views.settings.helpers import set_user_key
from kaleta.views.settings.user_prefs import (
    get_payee_automerge_enabled,
    get_payee_automerge_threshold,
)


class PayeeAutoMergeSettings:
    """Auto-merge toggle, its confidence threshold and a "run scan now" button.

    There is no background scheduler for the scan: it runs when the user
    presses the button, with the toggle and threshold as they are then.
    """

    def __init__(self) -> None:
        with ui.column().classes("w-full gap-1 mt-4").props("data-payee-automerge"):
            ui.label(t("settings.payee_automerge_hint")).classes("text-xs text-slate-500")
            ui.switch(
                t("settings.payee_automerge_enabled"),
                value=get_payee_automerge_enabled(),
                on_change=lambda e: set_user_key("payee_automerge_enabled", bool(e.value)),
            )
            threshold = get_payee_automerge_threshold()
            threshold_label = ui.label(
                t("settings.payee_automerge_threshold", value=f"{threshold:.2f}")
            ).classes("text-sm mt-2")
            ui.slider(
                min=AUTO_MERGE_THRESHOLD_MIN,
                max=AUTO_MERGE_THRESHOLD_MAX,
                step=0.01,
                value=threshold,
            ).props("label").classes("max-w-80").on(
                "change",
                lambda e: self._save_threshold(e.args, threshold_label),
            )
            ui.button(
                t("settings.payee_automerge_run"),
                icon="manage_search",
                on_click=self._run_scan,
            ).props("color=primary outline").classes("mt-2")

    @staticmethod
    def _save_threshold(raw: object, label: ui.label) -> None:
        value = round(float(str(raw)), 2)
        label.set_text(t("settings.payee_automerge_threshold", value=f"{value:.2f}"))
        set_user_key("payee_automerge_threshold", value)

    @staticmethod
    async def _run_scan() -> None:
        threshold = get_payee_automerge_threshold() if get_payee_automerge_enabled() else None

        async def _scan(session: Any) -> MergeScanResult:
            return await PayeeMergeService(session).scan(auto_merge_threshold=threshold)

        try:
            result = await with_session(_scan)
        except Exception as exc:
            if handle_kaleta_error(exc):
                return
            raise
        ui.notify(
            t(
                "settings.payee_automerge_done",
                merged=len(result.merged),
                proposals=len(result.proposals),
            ),
            type="positive",
        )
