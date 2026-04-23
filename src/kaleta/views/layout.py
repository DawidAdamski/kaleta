from collections.abc import Callable, Generator
from contextlib import contextmanager
from importlib.metadata import version as _pkg_version
from typing import Any

from nicegui import app, ui

from kaleta.i18n import t
from kaleta.pwa import PWA_HEAD
from kaleta.views.theme import (
    DARK_CSS,
    DRAWER,
    HEADER,
    NAV_GROUP,
    NAV_GROUP_ROW,
    NAV_ITEM,
    PAGE_CONTAINER,
    PAGE_SHELL,
)

try:
    _APP_VERSION = f"v{_pkg_version('kaleta')}"
except Exception:
    _APP_VERSION = "v0.1.0"

# Groups: (group_key, [(icon, path, label_key), ...])
NAV_GROUPS: list[tuple[str, list[tuple[str, str, str]]]] = [
    (
        "nav.group_overview",
        [
            ("dashboard", "/", "nav.dashboard"),
            ("account_balance_wallet", "/accounts", "nav.accounts"),
            ("pie_chart", "/net-worth", "nav.net_worth"),
            ("assessment", "/reports", "nav.reports"),
        ],
    ),
    (
        "nav.group_manage",
        [
            ("receipt_long", "/transactions", "nav.transactions"),
            ("calendar_month", "/payment-calendar", "nav.payment_calendar"),
            ("bar_chart", "/budgets", "nav.budgets"),
            ("edit_note", "/budget-plan", "nav.budget_plan"),
            ("upload_file", "/import", "nav.import"),
        ],
    ),
    (
        "nav.group_tools",
        [
            ("insights", "/forecast", "nav.forecast"),
            ("calculate", "/credit-calculator", "nav.credit_calculator"),
            ("credit_card", "/credit", "nav.credit"),
            ("auto_awesome", "/wizard", "nav.wizard"),
            ("cleaning_services", "/housekeeping", "nav.housekeeping"),
        ],
    ),
    (
        "nav.group_setup",
        [
            ("account_balance", "/institutions", "nav.institutions"),
            ("category", "/categories", "nav.categories"),
            ("label", "/tags", "nav.tags"),
            ("person_search", "/payees", "nav.payees"),
            ("settings", "/settings", "nav.settings"),
        ],
    ),
]


@contextmanager
def page_layout(title: str, *, wide: bool = False) -> Generator[None]:
    """Shared layout: header + left drawer + main content area."""
    from kaleta.config.setup_config import is_configured

    ui.add_head_html(PWA_HEAD)
    ui.add_head_html(f"<style>{DARK_CSS}</style>")

    if not is_configured():
        ui.navigate.to("/setup")
        yield
        return

    is_dark: bool = app.storage.user.get("dark_mode", False)
    is_mini: bool = app.storage.user.get("sidebar_mini", False)

    dark_mode = ui.dark_mode(value=is_dark)
    drawer: Any
    toggle_btn: Any
    mini_btn: Any
    close_dialog: Any

    def toggle_dark() -> None:
        dark_mode.toggle()
        app.storage.user["dark_mode"] = dark_mode.value
        toggle_btn.props(f"icon={'light_mode' if dark_mode.value else 'dark_mode'}")

    def toggle_mini() -> None:
        new_mini = not app.storage.user.get("sidebar_mini", False)
        app.storage.user["sidebar_mini"] = new_mini
        if new_mini:
            drawer.props("mini mini-to-overlay")
        else:
            drawer.props(remove="mini mini-to-overlay")
        mini_btn.props(f"icon={'chevron_right' if new_mini else 'chevron_left'}")

    ui.query("body").classes(PAGE_SHELL)

    with ui.header().classes(f"{HEADER} items-center px-4 gap-4 h-16"):
        ui.button(icon="menu", on_click=lambda: drawer.toggle()).props(
            "flat round dense color=primary"
        )
        mini_btn = (
            ui.button(
                icon="chevron_right" if is_mini else "chevron_left",
                on_click=toggle_mini,
            )
            .props("flat round dense color=primary")
            .tooltip(t("common.toggle_sidebar"))
        )
        ui.label("Kaleta").classes("text-xl font-bold tracking-tight text-primary")
        ui.space()
        ui.label(title).classes("text-sm text-slate-500")
        toggle_btn = (
            ui.button(
                icon="light_mode" if is_dark else "dark_mode",
                on_click=toggle_dark,
            )
            .props("flat round dense color=primary")
            .tooltip(t("common.toggle_dark"))
        )

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
        ).props("flat round dense color=primary").tooltip(t("common.close_db"))

    with ui.left_drawer(value=True).classes(DRAWER) as drawer:
        if is_mini:
            drawer.props("mini mini-to-overlay")
        # Collapse state persisted per user across page loads
        nav_collapsed: dict[str, bool] = dict(app.storage.user.get("nav_collapsed", {}))

        for group_key, items in NAV_GROUPS:
            is_col = nav_collapsed.get(group_key, False)

            # Clickable group header
            with ui.row().classes(NAV_GROUP_ROW) as hdr:
                ui.label(t(group_key)).classes(NAV_GROUP)
                chevron = ui.icon(
                    "keyboard_arrow_down" if is_col else "keyboard_arrow_up", size="xs"
                ).classes("text-slate-400")

            # Items container — hidden when collapsed
            with ui.column().classes("w-full gap-0") as items_col:
                for icon, path, key in items:
                    with ui.item(on_click=lambda p=path: ui.navigate.to(p)).classes(NAV_ITEM):
                        with ui.item_section().props("avatar"):
                            ui.icon(icon).classes("text-primary")
                        with ui.item_section():
                            ui.item_label(t(key))

            items_col.set_visibility(not is_col)

            # Toggle callback — captures loop vars via default args to avoid closure bug
            def _make_toggle(gk: str, col: ui.column, ch: ui.icon) -> Callable[[], None]:
                def _toggle() -> None:
                    stored: dict[str, bool] = dict(app.storage.user.get("nav_collapsed", {}))
                    now_col = not stored.get(gk, False)
                    stored[gk] = now_col
                    app.storage.user["nav_collapsed"] = stored
                    col.set_visibility(not now_col)
                    ch.props(f"name={'keyboard_arrow_down' if now_col else 'keyboard_arrow_up'}")

                return _toggle

            hdr.on("click", _make_toggle(group_key, items_col, chevron))

        ui.separator().classes("mx-4 my-2 opacity-60")
        with ui.item(on_click=lambda: ui.navigate.to("/api-docs", new_tab=True)).classes(NAV_ITEM):
            with ui.item_section().props("avatar"):
                ui.icon("api").classes("text-secondary")
            with ui.item_section():
                ui.item_label(t("nav.api_docs"))

        ui.space()
        ui.label(_APP_VERSION).classes("k-app-version text-xs text-grey-4 text-center pb-3 w-full")

    # ── Keyboard shortcuts help dialog (press ?) ──────────────────────────
    with ui.dialog() as shortcuts_dialog, ui.card().classes("w-[480px] gap-3"):
        ui.label(t("common.shortcuts_help")).classes("text-lg font-bold")
        ui.label(t("common.shortcuts_global")).classes("text-sm font-semibold text-grey-6 mt-2")
        with ui.grid(columns=2).classes("w-full gap-x-8 gap-y-1"):
            ui.label("Alt+N").classes("font-mono text-sm text-primary font-bold")
            ui.label(t("common.shortcut_new_tx")).classes("text-sm")
            ui.label("?").classes("font-mono text-sm text-primary font-bold")
            ui.label(t("common.shortcut_open_help")).classes("text-sm")
        ui.label(t("common.shortcuts_transactions")).classes(
            "text-sm font-semibold text-grey-6 mt-3"
        )
        with ui.grid(columns=2).classes("w-full gap-x-8 gap-y-1"):
            ui.label("Enter").classes("font-mono text-sm text-primary font-bold")
            ui.label(t("common.shortcut_submit")).classes("text-sm")
            ui.label("Escape").classes("font-mono text-sm text-primary font-bold")
            ui.label(t("common.shortcut_close")).classes("text-sm")
        with ui.row().classes("w-full justify-end mt-2"):
            ui.button(t("common.close"), on_click=shortcuts_dialog.close).props("flat")

    # ── Global keyboard shortcut: Alt+N → new transaction from any page ──
    # On /transactions the page-local handler opens the dialog directly.
    # From any other page we navigate to /transactions?new=1 so the dialog
    # auto-opens on arrival.
    async def _global_key(e: Any) -> None:
        if not getattr(e, "action", None) or not e.action.keydown:
            return
        key = getattr(e, "key", None)
        no_mod = not getattr(e.modifiers, "ctrl", False) and not getattr(e.modifiers, "alt", False)
        alt_only = getattr(e.modifiers, "alt", False) and not getattr(e.modifiers, "ctrl", False)
        if key == "?" and no_mod:
            shortcuts_dialog.open()
        elif key == "n" and alt_only:
            is_tx_page = await ui.run_javascript("window.location.pathname === '/transactions'")
            if not is_tx_page:
                ui.navigate.to("/transactions?new=1")

    ui.keyboard(on_key=_global_key, active=True)

    width_cls = "max-w-screen-2xl" if wide else "max-w-7xl"
    with ui.column().classes(f"{PAGE_CONTAINER} {width_cls}"):
        yield
