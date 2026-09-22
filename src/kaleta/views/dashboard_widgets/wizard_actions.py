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
from kaleta.views.dashboard_widgets.registry import RenderContext, register
from kaleta.views.theme import (
    ACCENT_SURFACE,
    ATTENTION_COUNT,
    ATTENTION_DOT,
    ATTENTION_ROW,
    ATTENTION_TEXT,
    BODY_MUTED,
    DASH_CARD,
    MUTED_STRONG,
    ON_ACCENT,
)

# Out of scope: pagination. Show at most this many rows, then a "+N more" tail.
MAX_ROWS = 12

# Severity on an accent fill cannot be a coloured dot — terracotta on apricot
# is unreadable — so it is carried by the glyph instead, which also stops
# severity from depending on colour vision (KAL-WAC-003).
_SEVERITY_ICON: dict[ActionSeverity, str] = {
    ActionSeverity.DANGER: "error",
    ActionSeverity.WARNING: "warning",
    ActionSeverity.INFO: "info",
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
        .classes("k-banner-item items-center gap-1.5 no-wrap cursor-pointer")
        .props(f'data-action-kind="{item.kind.value}" data-severity="{item.severity.value}"')
        .on("click", lambda _e=None, href=item.href: ui.navigate.to(href))
    ):
        ui.icon(_SEVERITY_ICON[item.severity], size="1rem").classes(f"{ON_ACCENT} shrink-0")
        ui.label(t(item.title_key, **params)).classes("text-[15px] font-medium")


def _row_body(label: str) -> None:
    """The three things in a phone row: bullet, message, chevron.

    Shared so the items and the "+N more" tail cannot drift into two
    different-looking rows in the same card.
    """
    ui.element("span").classes(ATTENTION_DOT)
    ui.label(label).classes(ATTENTION_TEXT)
    ui.icon("chevron_right", size="16px").classes(f"{MUTED_STRONG} shrink-0")


def _row_element(href: str) -> ui.element:
    """A 44px row that goes to *href* — by tap, by click or from the keyboard.

    The row is the target, so it has to be one: a bare ``div`` with a click
    handler is unreachable without a pointer, and on a phone these rows are
    the only way into the items (`1f` gives the card no "Open" pill). Enter
    and Space, the two keys a ``role="button"`` promises. No `aria-label` —
    the row's own text is its accessible name, and a copy of it in an
    attribute is a second string to keep in step with the first.
    """
    row = ui.element("div").classes(ATTENTION_ROW).props('tabindex="0" role="button"')
    for event in ("click", "keydown.enter", "keydown.space.prevent"):
        row.on(event, lambda _e=None, target=href: ui.navigate.to(target))
    return row


def _render_card_row(item: ActionItem) -> None:
    """One action as artboard `1f` draws it on a phone.

    A 44px row — the handoff's floor for a thumb, and the reason the desktop
    banner's inline list cannot simply be narrowed: there the items run into
    one another separated by middots, which is a paragraph, not a set of
    targets. The kind and severity attributes are the banner's, so the
    ranking and routing tests read the same DOM at either width.
    """
    params = _message_params(item)
    label = t(item.title_key, **params)
    with _row_element(item.href).props(
        f'data-action-kind="{item.kind.value}" data-severity="{item.severity.value}"'
    ):
        _row_body(label)


def _render_attention_card(items: list[ActionItem]) -> None:
    """The phone's "Needs attention": paper, an eyebrow, a count, then rows."""
    shown = items[:MAX_ROWS]
    with ui.card().classes(f"{DASH_CARD} gap-0"):
        with ui.row().classes("w-full items-center justify-between no-wrap mb-2"):
            ui.label(t("dashboard_widgets.wizard_actions")).classes("k-eyebrow")
            ui.label(str(len(items))).classes(ATTENTION_COUNT)
        for item in shown:
            _render_card_row(item)
        if len(items) > MAX_ROWS:
            # The tail is a row like the others rather than a caption: it is
            # the only way to the rest of the list, and the wizard is where
            # the rest of it lives. The phone card carries no "Open" pill —
            # `1f` makes every row its own target instead.
            with _row_element("/wizard"):
                _row_body(t("dashboard_widgets.wizard_actions_more", count=len(items) - MAX_ROWS))


@register(
    "wizard_actions",
    "dashboard_widgets.wizard_actions",
    "checklist",
    (4, 1),
    ((4, 1), (4, 2)),
)
async def render_wizard_actions(session: AsyncSession, ctx: RenderContext) -> None:
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

    if ctx.narrow:
        _render_attention_card(items)
        return

    shown = items[:MAX_ROWS]
    with (
        ui.element("div").classes(f"{ACCENT_SURFACE} k-banner w-full rounded-[14px]"),
        # Wraps rather than `no-wrap`: on a phone the banner is full width and
        # `no-wrap` squeezed the message into a two-word column beside a button
        # that kept its own width. With room it still sits on one line.
        ui.row().classes("w-full items-center gap-[18px] px-6 py-[18px]"),
    ):
        ui.icon("auto_awesome", size="22px").classes(ON_ACCENT)
        # A floor, not `min-w-0`: a flex item shrinks before its row wraps, so
        # with nothing to stop it the message column collapsed to one word per
        # line beside a button that would not give up any width.
        with ui.column().classes("gap-[3px] flex-1 min-w-[180px]"):
            ui.label(t("dashboard_widgets.wizard_actions")).classes(f"k-eyebrow {ON_ACCENT}")
            with ui.row().classes("items-baseline gap-2 flex-wrap wizard-actions-list"):
                for index, item in enumerate(shown):
                    if index:
                        ui.label("·").classes("text-[15px] opacity-60")
                    _render_row(item)
                if len(items) > MAX_ROWS:
                    ui.label(
                        t("dashboard_widgets.wizard_actions_more", count=len(items) - MAX_ROWS)
                    ).classes("text-sm opacity-80")
        # `color=None`: Quasar's colour helpers are `!important`, so a button
        # that keeps NiceGUI's default `primary` cannot be given the paper
        # the artboard fills this pill with by any stylesheet rule — it drew
        # the accent on the accent, which is a label and not a button.
        ui.button(
            t("dashboard_widgets.wizard_actions_open"),
            on_click=lambda: ui.navigate.to("/wizard"),
            color=None,
        ).props("unelevated no-caps dense").classes("k-banner-btn shrink-0")
