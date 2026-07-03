"""Settings page — routing, layout, and tab wiring."""

from __future__ import annotations

from typing import Any

from nicegui import app, ui

from kaleta.i18n import t
from kaleta.services import AccountService, CurrencyRateService, with_session
from kaleta.views.layout import page_layout
from kaleta.views.settings.about_tab import render_about_tab
from kaleta.views.settings.appearance_tab import render_appearance_tab
from kaleta.views.settings.data_tab import render_data_tab
from kaleta.views.settings.features_tab import render_features_tab
from kaleta.views.settings.general_tab import render_general_tab
from kaleta.views.settings.history_tab import render_history_tab


async def settings_page() -> None:
    default_currency: str = app.storage.user.get("currency", "PLN")

    async def _load_data_context(session: Any) -> tuple[str, list[str], list[tuple[str, str]]]:
        accounts = await AccountService(session).list()
        rate_svc = CurrencyRateService(session)
        rate_pairs = await rate_svc.list_pairs()
        account_currencies = {account.currency for account in accounts}
        foreign_currencies = sorted(c for c in account_currencies if c != default_currency)
        relevant_pairs = rate_svc.build_relevant_pairs(
            default_currency,
            account_currencies,
            rate_pairs,
        )
        return default_currency, foreign_currencies, relevant_pairs

    _, foreign_currencies, relevant_pairs = await with_session(_load_data_context)

    with page_layout(t("settings.title")):
        ui.label(t("settings.title")).classes("text-2xl font-bold")

        with ui.tabs().classes("w-full") as tabs:
            general_tab = ui.tab("general", label=t("settings.tab_general"), icon="tune")
            appearance_tab = ui.tab(
                "appearance", label=t("settings.tab_appearance"), icon="palette"
            )
            features_tab = ui.tab("features", label=t("settings.tab_features"), icon="toggle_on")
            data_tab = ui.tab("data", label=t("settings.tab_data"), icon="storage")
            history_tab = ui.tab("history", label=t("settings.tab_history"), icon="history")
            about_tab = ui.tab("about", label=t("settings.tab_about"), icon="info")

        with ui.tab_panels(tabs, value=general_tab).classes("w-full"):
            with ui.tab_panel(general_tab):
                render_general_tab()
            with ui.tab_panel(appearance_tab):
                render_appearance_tab()
            with ui.tab_panel(features_tab):
                render_features_tab()
            with ui.tab_panel(data_tab):
                await render_data_tab(
                    default_currency=default_currency,
                    foreign_currencies=foreign_currencies,
                    relevant_pairs=relevant_pairs,
                )
            with ui.tab_panel(history_tab):
                await render_history_tab()
            with ui.tab_panel(about_tab):
                render_about_tab()
