# SPDX-License-Identifier: AGPL-3.0-or-later
"""Wizard action-items widget — what needs attention across every section."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from nicegui import app, ui

from kaleta.i18n import t
from kaleta.schemas.wizard_actions import ActionItem, ActionSeverity
from kaleta.services import WizardActionService
from kaleta.views.dashboard_widgets.helpers import section_card
from kaleta.views.dashboard_widgets.registry import register
from kaleta.views.theme import BODY_MUTED

# Out of scope: pagination. Show at most this many rows, then a "+N more" tail.
MAX_ROWS = 12

_SEVERITY_DOT: dict[ActionSeverity, str] = {
    ActionSeverity.DANGER: "bg-red-500",
    ActionSeverity.WARNING: "bg-amber-500",
    ActionSeverity.INFO: "bg-sky-500",
}


def drop_dismissed(items: list[ActionItem], dismissed: set[str]) -> list[ActionItem]:
    """Hide mentor hints the user dismissed on the wizard page.

    Pure on purpose — the caller supplies *dismissed*, because those keys live
    in ``app.storage.user`` (browser-scoped), which the services layer cannot
    read. Non-mentor items have no ``dismiss_key`` and always survive.
    """
    if not dismissed:
        return items
    return [i for i in items if i.dismiss_key is None or i.dismiss_key not in dismissed]


def _dismissed_mentor_keys() -> set[str]:
    """The keys ``views/wizard.py`` writes when the user dismisses a hint."""
    return set(app.storage.user.get("wizard_mentor_dismissed", []))


def _message_params(item: ActionItem) -> dict[str, str | int]:
    """Interpolation values for an item's title/body, including its ``count``."""
    params: dict[str, str | int] = dict(item.params)
    if item.count is not None:
        params["count"] = item.count
    return params


def _render_row(item: ActionItem) -> None:
    with (
        ui.row()
        .classes(
            "w-full items-start gap-2 no-wrap cursor-pointer rounded px-1 py-1 "
            "hover:bg-slate-100 dark:hover:bg-slate-700/40"
        )
        .props(f'data-action-kind="{item.kind.value}" data-severity="{item.severity.value}"')
        .on("click", lambda _e=None, href=item.href: ui.navigate.to(href))
    ):
        ui.element("div").classes(
            f"h-2 w-2 rounded-full shrink-0 mt-1.5 {_SEVERITY_DOT[item.severity]}"
        )
        params = _message_params(item)
        with ui.column().classes("gap-0 min-w-0 flex-1"):
            ui.label(t(item.title_key, **params)).classes("text-sm leading-tight")
            ui.label(t(item.body_key, **params)).classes("text-xs text-slate-500 leading-tight")


@register(
    "wizard_actions",
    "dashboard_widgets.wizard_actions",
    "checklist",
    (2, 2),
    ((2, 2), (4, 2)),
)
async def render_wizard_actions(session: AsyncSession, is_dark: bool) -> None:  # noqa: ARG001
    items = drop_dismissed(
        await WizardActionService(session).get_action_items(), _dismissed_mentor_keys()
    )

    with section_card(
        t("dashboard_widgets.wizard_actions"),
        subtitle=t("dashboard_widgets.wizard_actions_sub"),
    ):
        if not items:
            ui.label(t("dashboard_widgets.wizard_actions_empty")).classes(
                f"{BODY_MUTED} wizard-actions-empty"
            )
        else:
            shown = items[:MAX_ROWS]
            with ui.column().classes("w-full gap-2 mt-1 wizard-actions-list"):
                # Grouped by section, but the ranked order decides which
                # section leads — the most urgent item brings its group up.
                for section in dict.fromkeys(i.section for i in shown):
                    ui.label(t(f"wizard_actions.section_{section.value}")).classes(
                        "text-[11px] font-semibold uppercase tracking-wide text-slate-400 mt-1"
                    )
                    for item in shown:
                        if item.section is section:
                            _render_row(item)
            if len(items) > MAX_ROWS:
                ui.label(
                    t("dashboard_widgets.wizard_actions_more", count=len(items) - MAX_ROWS)
                ).classes(f"{BODY_MUTED} mt-1")

        ui.button(
            t("dashboard_widgets.wizard_actions_open"),
            icon="auto_awesome",
            on_click=lambda: ui.navigate.to("/wizard"),
        ).props("flat dense color=primary size=sm").classes("mt-2 self-start")
