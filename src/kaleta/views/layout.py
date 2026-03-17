from collections.abc import Generator
from contextlib import contextmanager
from importlib.metadata import version as _pkg_version

from nicegui import app, ui

from kaleta.i18n import t

try:
    _APP_VERSION = f"v{_pkg_version('kaleta')}"
except Exception:
    _APP_VERSION = "v0.1.0"

# Groups: (group_key, [(icon, path, label_key), ...])
NAV_GROUPS: list[tuple[str, list[tuple[str, str, str]]]] = [
    ("nav.group_overview", [
        ("dashboard", "/", "nav.dashboard"),
        ("account_balance_wallet", "/accounts", "nav.accounts"),
        ("pie_chart", "/net-worth", "nav.net_worth"),
        ("assessment", "/reports", "nav.reports"),
    ]),
    ("nav.group_manage", [
        ("receipt_long", "/transactions", "nav.transactions"),
        ("event_repeat", "/planned", "nav.planned"),
        ("bar_chart", "/budgets", "nav.budgets"),
        ("edit_note", "/budget-plan", "nav.budget_plan"),
        ("upload_file", "/import", "nav.import_csv"),
        ("auto_awesome", "/wizard", "nav.wizard"),
    ]),
    ("nav.group_tools", [
        ("insights", "/forecast", "nav.forecast"),
        ("calculate", "/credit-calculator", "nav.credit_calculator"),
    ]),
    ("nav.group_setup", [
        ("account_balance", "/institutions", "nav.institutions"),
        ("category", "/categories", "nav.categories"),
        ("label", "/tags", "nav.tags"),
        ("settings", "/settings", "nav.settings"),
    ]),
]


@contextmanager
def page_layout(title: str, *, wide: bool = False) -> Generator[None]:
    """Shared layout: header + left drawer + main content area."""
    from kaleta.config.setup_config import is_configured

    if not is_configured():
        ui.navigate.to("/setup")
        yield
        return

    is_dark: bool = app.storage.user.get("dark_mode", False)

    dark_mode = ui.dark_mode(value=is_dark)

    def toggle_dark() -> None:
        dark_mode.toggle()
        app.storage.user["dark_mode"] = dark_mode.value
        toggle_btn.props(f"icon={'light_mode' if dark_mode.value else 'dark_mode'}")

    with ui.header().classes("bg-primary text-white items-center px-4 gap-4"):
        ui.button(icon="menu", on_click=lambda: drawer.toggle()).props(
            "flat round dense color=white"
        )
        ui.label("Kaleta").classes("text-xl font-bold")
        ui.space()
        ui.label(title).classes("text-sm opacity-80")
        toggle_btn = ui.button(
            icon="light_mode" if is_dark else "dark_mode",
            on_click=toggle_dark,
        ).props("flat round dense color=white").tooltip(t("common.toggle_dark"))

        async def _close_db() -> None:
            from kaleta.config.setup_config import clear_db
            from kaleta.db import AsyncSessionFactory

            close_dialog.close()
            clear_db()
            await AsyncSessionFactory.dispose()
            ui.navigate.to("/setup")

        with ui.dialog() as close_dialog, ui.card():
            ui.label(t("common.close_confirm")).classes("text-base")
            with ui.row().classes("justify-end gap-2 mt-4"):
                ui.button(t("common.cancel"), on_click=close_dialog.close).props("flat")
                ui.button(
                    t("common.close_db"),
                    icon="eject",
                    on_click=_close_db,
                ).props("color=negative unelevated")

        ui.button(
            icon="eject",
            on_click=close_dialog.open,
        ).props("flat round dense color=white").tooltip(t("common.close_db"))

    with ui.left_drawer(value=True).classes("pt-2") as drawer:
        # Collapse state persisted per user across page loads
        nav_collapsed: dict[str, bool] = dict(app.storage.user.get("nav_collapsed", {}))

        for group_key, items in NAV_GROUPS:
            is_col = nav_collapsed.get(group_key, False)

            # Clickable group header
            with ui.row().classes(
                "items-center px-3 pt-2 pb-1 mx-1 rounded-lg cursor-pointer select-none"
                " hover:bg-grey-2"
            ) as hdr:
                ui.label(t(group_key)).classes(
                    "text-xs text-grey-5 uppercase tracking-wider font-medium flex-1"
                )
                chevron = ui.icon(
                    "keyboard_arrow_down" if is_col else "keyboard_arrow_up", size="xs"
                ).classes("text-grey-4")

            # Items container — hidden when collapsed
            with ui.column().classes("w-full gap-0") as items_col:
                for icon, path, key in items:
                    with ui.item(on_click=lambda p=path: ui.navigate.to(p)).classes(
                        "rounded-lg mx-2 mb-0.5 cursor-pointer hover:bg-grey-3"
                    ):
                        with ui.item_section().props("avatar"):
                            ui.icon(icon).classes("text-primary")
                        with ui.item_section():
                            ui.item_label(t(key))

            items_col.set_visibility(not is_col)

            # Toggle callback — captures loop vars via default args to avoid closure bug
            def _make_toggle(gk: str, col: ui.column, ch: ui.icon) -> object:
                def _toggle() -> None:
                    stored: dict[str, bool] = dict(app.storage.user.get("nav_collapsed", {}))
                    now_col = not stored.get(gk, False)
                    stored[gk] = now_col
                    app.storage.user["nav_collapsed"] = stored
                    col.set_visibility(not now_col)
                    ch.props(
                        f"name={'keyboard_arrow_down' if now_col else 'keyboard_arrow_up'}"
                    )
                return _toggle

            hdr.on("click", _make_toggle(group_key, items_col, chevron))

        ui.separator().classes("mx-4 my-2")
        with ui.item(on_click=lambda: ui.navigate.to("/api-docs", new_tab=True)).classes(
            "rounded-lg mx-2 mb-1 cursor-pointer hover:bg-grey-3"
        ):
            with ui.item_section().props("avatar"):
                ui.icon("api").classes("text-secondary")
            with ui.item_section():
                ui.item_label(t("nav.api_docs"))

        ui.space()
        ui.label(_APP_VERSION).classes("text-xs text-grey-4 text-center pb-3 w-full")

    width_cls = "max-w-screen-2xl" if wide else "max-w-7xl"
    with ui.column().classes(f"w-full {width_cls} mx-auto p-6 gap-4"):
        yield
