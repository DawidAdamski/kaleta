# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared auth page chrome — a two-panel split (artboard 3f).

A single-user self-hosted app does not need a card floating in a centred
viewport. The form sits on the sand ground at the left under the wordmark;
an ink panel at the right carries one line of copy and three counts read
from the ledger. Below ``md`` the panel is gone and the form has the screen.
"""

from __future__ import annotations

import logging
from typing import Any

from nicegui import ui

from kaleta.i18n import t
from kaleta.pwa import PWA_HEAD
from kaleta.services import with_session
from kaleta.services.auth_stats_service import AuthLandingStats, AuthStatsService
from kaleta.views.theme import (
    AUTH_PANEL,
    AUTH_PANEL_FIGURE,
    AUTH_PANEL_LABEL,
    BODY_MUTED,
    INK,
    PAGE_SHELL,
    SECTION_HEADING,
    apply_brand,
    theme_css,
)

logger = logging.getLogger(__name__)

#: Every control on an auth page is at least this tall. On a phone the form
#: is the whole screen, and a 40px field in the middle of it is a target the
#: thumb has to aim at.
AUTH_CONTROL = "min-h-[48px]"


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
        with (
            ui.column().classes("flex-1 min-w-0 items-center justify-center p-8 md:p-12 gap-5"),
            ui.column().classes("w-full max-w-md gap-5") as form_column,
        ):
            with ui.row().classes("items-center gap-3"):
                ui.icon("account_balance_wallet", size="2rem").classes(INK)
                ui.label("Kaleta").classes(f"{INK} text-3xl font-light tracking-tight")
            with ui.column().classes("w-full gap-1"):
                ui.label(t(title_key)).classes(SECTION_HEADING)
                ui.label(t(subtitle_key)).classes(BODY_MUTED)

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
    """The ink panel: one line about the app, and what is already in it."""
    with ui.column().classes(
        f"{AUTH_PANEL} w-[40%] max-w-[560px] flex-none justify-center gap-10 p-12"
    ):
        ui.label(t("auth.panel_copy")).classes("text-[19px] leading-relaxed font-light max-w-sm")
        if stats is None:
            return
        with ui.row().classes("gap-10 flex-wrap"):
            for value, label_key in (
                (stats.transactions, "auth.panel_count_transactions"),
                (stats.accounts, "auth.panel_count_accounts"),
                (stats.months, "auth.panel_count_months"),
            ):
                with ui.column().classes("gap-1"):
                    ui.label(f"{value:,}".replace(",", " ")).classes(AUTH_PANEL_FIGURE)
                    ui.label(t(label_key)).classes(AUTH_PANEL_LABEL)
