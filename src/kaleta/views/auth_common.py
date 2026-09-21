# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared auth page chrome — a two-panel split (artboard 3f).

A single-user self-hosted app does not need a card floating in a centred
viewport. The form sits on the sand ground at the left under the wordmark;
an ink panel at the right carries one line of copy and three counts read
from the ledger. Below ``md`` the panel is gone and the form has the screen.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from typing import Any

from nicegui import ui

from kaleta.i18n import t
from kaleta.pwa import PWA_HEAD
from kaleta.services import with_session
from kaleta.services.auth_stats_service import AuthLandingStats, AuthStatsService
from kaleta.views.components.amount_label import spaced_thousands
from kaleta.views.theme import (
    ACCENT_TEXT,
    AUTH_FIELD,
    AUTH_FIELD_LABEL,
    AUTH_FOOT,
    AUTH_PANEL,
    AUTH_PANEL_FIGURE,
    AUTH_PANEL_LABEL,
    AUTH_PANEL_RULE,
    AUTH_SUBTITLE,
    AUTH_TITLE,
    BUTTON_INK_WIDE,
    ERROR_SLOT,
    ERROR_SLOT_EMPTY,
    INK,
    PAGE_SHELL,
    apply_brand,
    theme_css,
)

logger = logging.getLogger(__name__)

#: Every control on an auth page is at least this tall. On a phone the form
#: is the whole screen, and a 40px field in the middle of it is a target the
#: thumb has to aim at.
AUTH_CONTROL = "min-h-[48px]"

#: The licence the foot of the form column names beside the version. Spelled
#: out rather than read from the metadata: `pyproject` carries the SPDX
#: expression, and "AGPL-3.0-or-later" is not what a login page should say.
LICENCE = "AGPL-3.0"


def app_version() -> str:
    """``v0.1.0`` — the same string the drawer's foot carries."""
    try:
        return f"v{_pkg_version('kaleta')}"
    except PackageNotFoundError:  # a source checkout has no metadata
        return "v0.1.0"


def auth_field(
    label_key: str,
    *,
    password: bool = False,
    password_toggle_button: bool = False,
) -> ui.input:
    """One field with its name above it, the way artboard `3f` draws them.

    Quasar floats a label inside the control; the artboard sets it outside as
    an eyebrow, which is what lets the field itself be a plain box.
    """
    with ui.column().classes("w-full gap-0"):
        ui.label(t(label_key)).classes(AUTH_FIELD_LABEL)
        field = (
            ui.input(password=password, password_toggle_button=password_toggle_button)
            .props("borderless")
            .classes(f"{AUTH_FIELD} w-full")
        )
        # Quasar's own label is what a screen reader reads; the eyebrow is
        # type on the page and announces nothing.
        field.props["aria-label"] = t(label_key)
    return field


def auth_error_slot() -> Callable[[str], None]:
    """The reserved strip for a message, and the one call that fills it.

    Artboard `3f` draws a failed login as a tinted box with an icon, always
    occupying its line: showing and hiding it moved the button down under the
    pointer at the moment the user was clicking it again, which is how a
    second attempt became a misclick. With nothing to say it keeps its height
    and drops its clothes, so the page is not carrying a pink box that says
    nothing.
    """
    with ui.row().classes(f"{ERROR_SLOT} {ERROR_SLOT_EMPTY} w-full") as slot:
        ui.icon("error_outline")
        label = ui.label("")

    def say(message: str) -> None:
        label.set_text(message)
        slot.classes(
            add=ERROR_SLOT_EMPTY if not message else "",
            remove="" if not message else ERROR_SLOT_EMPTY,
        )

    return say


def auth_submit(label_key: str, on_click: Callable[[], Any]) -> ui.button:
    """The one button on an auth page: ink, full width, and no icon.

    On artboard `3f` the accent belongs to the wordmark alone, and a page
    with a single action needs no mark to say which one it is.
    """
    return (
        ui.button(t(label_key), on_click=on_click, color=None)
        .props("unelevated no-caps")
        .classes(f"w-full {AUTH_CONTROL} {BUTTON_INK_WIDE}")
    )


async def auth_page_shell(title_key: str, subtitle_key: str) -> ui.column:
    """Paint the split and return the column the page's form goes into."""
    ui.add_head_html(PWA_HEAD)
    ui.add_head_html(f"<style>{theme_css()}</style>")
    apply_brand()
    ui.query("body").classes(PAGE_SHELL)
    # NiceGUI pads its content wrapper by 1rem, which would leave the ink
    # panel floating 16px short of every edge. This page is the panel.
    ui.query(".nicegui-content").classes("p-0 gap-0")

    stats = await _landing_stats()

    with ui.row().classes("w-full min-h-screen no-wrap gap-0 items-stretch"):
        # The wordmark at the top, the form in the middle, the version at the
        # foot: artboard `3f` spaces the column with two equal flexible gaps
        # rather than centring the lot.
        with ui.column().classes("flex-1 min-w-0 p-8 md:py-16 md:px-[60px] gap-0"):
            with ui.row().classes("items-center gap-[11px]"):
                ui.icon("account_balance_wallet", size="26px").classes(ACCENT_TEXT)
                ui.label("Kaleta").classes(f"{INK} text-[21px] font-semibold tracking-tight")
            ui.element("div").classes("flex-1 min-h-[36px]")
            with ui.column().classes("w-full max-w-[340px] gap-0") as form_column:
                ui.label(t(title_key)).classes(AUTH_TITLE)
                ui.label(t(subtitle_key)).classes(f"{AUTH_SUBTITLE} mt-2.5 mb-8")
            ui.element("div").classes("flex-1 min-h-[36px]")
            ui.label(f"{app_version()} · {LICENCE}").classes(AUTH_FOOT)

        _side_panel(stats)

    return form_column


async def _landing_stats() -> AuthLandingStats | None:
    """The counts, or nothing at all.

    A login page that will not render because the database is not there yet
    is worse than a login page without three numbers on it, so every failure
    here is the absence of the counts and never the absence of the page.
    """

    async def _read(session: Any) -> AuthLandingStats | None:
        return await AuthStatsService(session).landing_stats()

    try:
        return await with_session(_read)
    except Exception:  # noqa: BLE001 — see the docstring
        # The service catches its own read; this catches not getting a session
        # at all, which is what a database that has never been created looks
        # like. Logged so the two are told apart in a log rather than both
        # showing up as a panel with no numbers on it.
        logger.warning("Login panel stats could not be read", exc_info=True)
        return None


def _side_panel(stats: AuthLandingStats | None) -> None:
    """The ink panel: one line about the app, and what is already in it.

    Bottom-aligned, as artboard `3f` draws it — the copy and the counts sit
    on the foot of the panel, not in the middle of an empty one.
    """
    with ui.column().classes(
        f"{AUTH_PANEL} w-[37%] max-w-[560px] flex-none justify-end gap-0 py-16 px-10"
    ):
        ui.label(t("auth.panel_copy")).classes("text-[15px] leading-[1.7]")
        if stats is None:
            return
        with ui.row().classes(f"{AUTH_PANEL_RULE} w-full gap-[26px] flex-wrap"):
            for value, label_key in (
                (stats.transactions, "auth.panel_count_transactions"),
                (stats.accounts, "auth.panel_count_accounts"),
                (stats.months, "auth.panel_count_months"),
            ):
                with ui.column().classes("gap-[3px]"):
                    ui.label(spaced_thousands(f"{value:,}")).classes(AUTH_PANEL_FIGURE)
                    ui.label(t(label_key)).classes(AUTH_PANEL_LABEL)
