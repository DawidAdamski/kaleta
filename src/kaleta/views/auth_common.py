"""Shared auth page chrome."""

from __future__ import annotations

from nicegui import ui

from kaleta.i18n import t
from kaleta.pwa import PWA_HEAD
from kaleta.views.theme import DARK_CSS


def auth_page_shell(title_key: str, subtitle_key: str) -> ui.column:
    ui.add_head_html(PWA_HEAD)
    ui.add_head_html(f"<style>{DARK_CSS}</style>")
    with ui.column().classes("w-full min-h-screen items-center justify-center p-8 gap-6") as col:
        with ui.row().classes("items-center gap-3"):
            ui.icon("account_balance_wallet", size="3rem").classes("text-primary")
            ui.label("Kaleta").classes("text-4xl font-bold")
        ui.label(t(title_key)).classes("text-xl font-semibold text-center")
        ui.label(t(subtitle_key)).classes("text-sm text-grey-6 text-center max-w-md")
    return col
