# SPDX-License-Identifier: AGPL-3.0-or-later
"""Settings — Security tab (API bearer tokens)."""

from __future__ import annotations

import json
from typing import Any

from nicegui import app, ui

from kaleta.auth.session import SESSION_USER_ID
from kaleta.i18n import t
from kaleta.services import ApiTokenService, with_session


async def render_security_tab() -> None:
    user_id = app.storage.user.get(SESSION_USER_ID)
    if user_id is None:
        ui.label(t("settings.security_login_required")).classes("text-grey-6")
        return

    token_dialog = ui.dialog()
    created_token: dict[str, str] = {"value": ""}

    with token_dialog, ui.card().classes("p-6 w-full max-w-lg"):
        ui.label(t("settings.security_token_created_title")).classes("text-lg font-semibold mb-2")
        ui.label(t("settings.security_token_created_hint")).classes("text-sm text-grey-6 mb-4")
        token_field = (
            ui.input(
                label=t("settings.security_token_value"),
                value="",
            )
            .props("readonly")
            .classes("w-full font-mono")
        )
        with ui.row().classes("gap-2 mt-4"):
            ui.button(
                t("settings.security_copy_token"),
                icon="content_copy",
                on_click=lambda: ui.run_javascript(
                    f"navigator.clipboard.writeText({json.dumps(created_token['value'])})"
                ),
            ).props("outline")
            ui.button(t("common.close"), on_click=token_dialog.close).props("flat")

    with ui.card().classes("p-6 w-full"):
        with ui.row().classes("items-center gap-2 mb-1"):
            ui.icon("vpn_key", color="primary").classes("text-xl")
            ui.label(t("settings.security_api_tokens")).classes("text-lg font-semibold")
        ui.label(t("settings.security_api_tokens_hint")).classes("text-xs text-grey-6 mb-4")

        label_input = ui.input(
            label=t("settings.security_token_label"),
            placeholder=t("settings.security_token_label_placeholder"),
        ).classes("w-full max-w-md")

        async def _create_token() -> None:
            label = (label_input.value or "").strip()
            if not label:
                ui.notify(t("settings.security_token_label_required"), type="warning")
                return

            async def _create(session: Any) -> tuple[str, str]:
                token, raw = await ApiTokenService(session).create_token(
                    user_id=int(user_id),
                    label=label,
                )
                return token.label, raw

            try:
                _label, raw = await with_session(_create)
            except Exception as exc:
                ui.notify(
                    t("settings.security_token_create_failed", error=str(exc)),
                    type="negative",
                )
                return

            label_input.value = ""
            created_token["value"] = raw
            token_field.value = raw
            token_dialog.open()
            ui.notify(t("settings.security_token_created"), type="positive")
            tokens_table.refresh()

        ui.button(
            t("settings.security_create_token"),
            icon="add",
            on_click=_create_token,
        ).props("color=primary").classes("mb-6")

        @ui.refreshable
        async def tokens_table() -> None:
            async def _load(session: Any) -> list[Any]:
                return await ApiTokenService(session).list_tokens(user_id=int(user_id))

            tokens = await with_session(_load)
            if not tokens:
                ui.label(t("settings.security_no_tokens")).classes("text-grey-5 text-sm")
                return

            cols = [
                {
                    "name": "label",
                    "label": t("settings.security_col_label"),
                    "field": "label",
                    "align": "left",
                },
                {
                    "name": "created",
                    "label": t("settings.security_col_created"),
                    "field": "created",
                    "align": "left",
                },
                {
                    "name": "last_used",
                    "label": t("settings.security_col_last_used"),
                    "field": "last_used",
                    "align": "left",
                },
                {
                    "name": "status",
                    "label": t("settings.security_col_status"),
                    "field": "status",
                    "align": "left",
                },
                {
                    "name": "actions",
                    "label": "",
                    "field": "id",
                    "align": "right",
                },
            ]
            rows = [
                {
                    "id": token.id,
                    "label": token.label,
                    "created": token.created_at.strftime("%Y-%m-%d %H:%M"),
                    "last_used": (
                        token.last_used_at.strftime("%Y-%m-%d %H:%M")
                        if token.last_used_at
                        else t("settings.security_never_used")
                    ),
                    "status": (
                        t("settings.security_status_active")
                        if token.is_active
                        else t("settings.security_status_revoked")
                    ),
                    "revoked": not token.is_active,
                }
                for token in tokens
            ]
            table = (
                ui.table(columns=cols, rows=rows, row_key="id")
                .classes("w-full")
                .props("flat dense")
            )

            async def _revoke(token_id: int) -> None:
                async def _do_revoke(session: Any) -> None:
                    await ApiTokenService(session).revoke_token(
                        token_id=token_id,
                        user_id=int(user_id),
                    )

                await with_session(_do_revoke)
                ui.notify(t("settings.security_token_revoked"), type="positive")
                tokens_table.refresh()

            table.add_slot(
                "body-cell-actions",
                """
                <q-td :props="props">
                  <q-btn v-if="!props.row.revoked"
                         flat dense round icon="block" size="sm"
                         color="negative"
                         @click="$emit('revoke', props.row)" />
                </q-td>
                """,
            )
            table.on("revoke", lambda e: _revoke(int(e.args["id"])))

        await tokens_table()
