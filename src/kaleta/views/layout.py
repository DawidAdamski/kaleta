from contextlib import contextmanager
from typing import Generator

from nicegui import app, ui


NAV_ITEMS = [
    ("dashboard",              "/",              "Dashboard"),
    ("receipt_long",           "/transactions",  "Transactions"),
    ("account_balance_wallet", "/accounts",      "Accounts"),
    ("account_balance",        "/institutions",  "Institutions"),
    ("category",               "/categories",    "Categories"),
    ("bar_chart",              "/budgets",       "Budgets"),
    ("edit_note",              "/budget-plan",   "Budget Plan"),
    ("upload_file",            "/import",        "Import CSV"),
    ("insights",               "/forecast",      "Forecast"),
    ("pie_chart",              "/net-worth",        "Net Worth"),
    ("calculate",              "/credit-calculator", "Credit Calculator"),
]


@contextmanager
def page_layout(title: str) -> Generator[None, None, None]:
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
        ).props("flat round dense color=white").tooltip("Toggle dark mode")

    with ui.left_drawer(value=True).classes("pt-2") as drawer:
        ui.label("Navigation").classes("text-xs text-grey-6 px-4 py-2 uppercase tracking-wider")
        for icon, path, label in NAV_ITEMS:
            with ui.item(on_click=lambda p=path: ui.navigate.to(p)).classes(
                "rounded-lg mx-2 mb-1 cursor-pointer hover:bg-grey-3"
            ):
                with ui.item_section().props("avatar"):
                    ui.icon(icon).classes("text-primary")
                with ui.item_section():
                    ui.item_label(label)

    with ui.column().classes("w-full max-w-7xl mx-auto p-6 gap-4"):
        yield
