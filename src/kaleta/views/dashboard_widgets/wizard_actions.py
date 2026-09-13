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
from kaleta.views.theme import ACCENT_SURFACE, BODY_MUTED, ON_ACCENT

# Out of scope: pagination. Show at most this many rows, then a "+N more" tail.
MAX_ROWS = 12

_SEVERITY_DOT: dict[ActionSeverity, str] = {
    ActionSeverity.DANGER: "k-dot--danger",
    ActionSeverity.WARNING: "k-dot--warn",
    ActionSeverity.INFO: "k-dot--info",
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
    """One action as an inline banner item.

    Keeps ``data-action-kind`` / ``data-severity`` and the click-through so the
    ranking and routing tests read the same DOM as before the restyle.
    """
    params = _message_params(item)
    with (
        ui.row()
        .classes("k-banner-item items-baseline gap-1.5 no-wrap cursor-pointer")
        .props(f'data-action-kind="{item.kind.value}" data-severity="{item.severity.value}"')
        .on("click", lambda _e=None, href=item.href: ui.navigate.to(href))
    ):
        ui.label(t(item.title_key, **params)).classes("text-sm font-medium")


@register(
    "wizard_actions",
    "dashboard_widgets.wizard_actions",
    "checklist",
    (4, 1),
    ((4, 1), (4, 2)),
)
async def render_wizard_actions(session: AsyncSession, is_dark: bool) -> None:  # noqa: ARG001
    items = drop_dismissed(
        await WizardActionService(session).get_action_items(), _dismissed_mentor_keys()
    )

    if not items:
        # Nothing to shout about: a quiet card, not an accent banner.
        with section_card(t("dashboard_widgets.wizard_actions")):
            ui.label(t("dashboard_widgets.wizard_actions_empty")).classes(
                f"{BODY_MUTED} wizard-actions-empty"
            )
        return

    shown = items[:MAX_ROWS]
    with (
        ui.element("div").classes(f"{ACCENT_SURFACE} k-banner w-full rounded-[14px]"),
        ui.row().classes("w-full items-center gap-4 no-wrap px-6 py-4"),
    ):
        ui.icon("auto_awesome", size="1.3rem").classes(ON_ACCENT)
        with ui.column().classes("gap-0.5 min-w-0 flex-1"):
            ui.label(t("dashboard_widgets.wizard_actions")).classes(f"k-eyebrow {ON_ACCENT}")
            with ui.row().classes("items-baseline gap-2 flex-wrap wizard-actions-list"):
                for index, item in enumerate(shown):
                    if index:
                        ui.label("·").classes("text-sm opacity-60")
                    _render_row(item)
                if len(items) > MAX_ROWS:
                    ui.label(
                        t("dashboard_widgets.wizard_actions_more", count=len(items) - MAX_ROWS)
                    ).classes("text-sm opacity-80")
        ui.button(
            t("dashboard_widgets.wizard_actions_open"),
            on_click=lambda: ui.navigate.to("/wizard"),
        ).props("unelevated no-caps dense").classes("k-banner-btn shrink-0")
