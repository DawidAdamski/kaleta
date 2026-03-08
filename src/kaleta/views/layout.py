from collections.abc import Generator
from contextlib import contextmanager

from nicegui import app, ui

from kaleta.i18n import t

NAV_ITEMS = [
    ("dashboard", "/", "nav.dashboard"),
    ("receipt_long", "/transactions", "nav.transactions"),
    ("account_balance_wallet", "/accounts", "nav.accounts"),
    ("account_balance", "/institutions", "nav.institutions"),
    ("category", "/categories", "nav.categories"),
    ("bar_chart", "/budgets", "nav.budgets"),
    ("edit_note", "/budget-plan", "nav.budget_plan"),
    ("upload_file", "/import", "nav.import_csv"),
    ("insights", "/forecast", "nav.forecast"),
    ("assessment", "/reports", "nav.reports"),
    ("pie_chart", "/net-worth", "nav.net_worth"),
    ("calculate", "/credit-calculator", "nav.credit_calculator"),
    ("settings", "/settings", "nav.settings"),
]


@contextmanager
def page_layout(title: str) -> Generator[None]:
    """Shared layout: header + left drawer + main content area."""
    is_dark: bool = app.storage.user.get("dark_mode", False)

    dark_mode = ui.dark_mode(value=is_dark)

    def toggle_dark() -> None:
        dark_mode.toggle()
        app.storage.user["dark_mode"] = dark_mode.value
        toggle_btn.props(f"icon={'light_mode' if dark_mode.value else 'dark_mode'}")

    with ui.header().classes("bg-primary text-white items-center px-4 gap-4"):
        ui.button(icon="menu", on_click=lambda: drawer.toggle()).props("flat round dense color=white")
        ui.label("Kaleta").classes("text-xl font-bold")
        ui.space()
        ui.label(title).classes("text-sm opacity-80")
        toggle_btn = ui.button(
            icon="light_mode" if is_dark else "dark_mode",
            on_click=toggle_dark,
        ).props("flat round dense color=white").tooltip(t("common.toggle_dark"))

    with ui.left_drawer(value=True).classes("pt-2") as drawer:
        ui.label(t("nav.navigation")).classes(
            "text-xs text-grey-6 px-4 py-2 uppercase tracking-wider"
        )
        for icon, path, key in NAV_ITEMS:
            with ui.item(on_click=lambda p=path: ui.navigate.to(p)).classes(
                "rounded-lg mx-2 mb-1 cursor-pointer hover:bg-grey-3"
            ):
                with ui.item_section().props("avatar"):
                    ui.icon(icon).classes("text-primary")
                with ui.item_section():
                    ui.item_label(t(key))

        ui.separator().classes("mx-4 my-2")
        with ui.item(on_click=lambda: ui.navigate.to("/api-docs", new_tab=True)).classes(
            "rounded-lg mx-2 mb-1 cursor-pointer hover:bg-grey-3"
        ):
            with ui.item_section().props("avatar"):
                ui.icon("api").classes("text-secondary")
            with ui.item_section():
                ui.item_label(t("nav.api_docs"))

    with ui.column().classes("w-full max-w-7xl mx-auto p-6 gap-4"):
        yield
