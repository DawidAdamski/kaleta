# SPDX-License-Identifier: AGPL-3.0-or-later
from collections.abc import Callable, Generator
from contextlib import contextmanager
from importlib.metadata import version as _pkg_version
from typing import Any

from nicegui import app, ui

from kaleta.config import settings
from kaleta.i18n import t
from kaleta.pwa import PWA_HEAD
from kaleta.views.theme import (
    BODY_MUTED,
    DRAWER,
    DRAWER_CONTROLS,
    HEADER,
    INK,
    MUTED,
    NAV_GROUP,
    NAV_GROUP_ROW,
    NAV_ITEM,
    NAV_ITEM_ACTIVE,
    PAGE_CONTAINER,
    PAGE_SHELL,
    PALETTE_CARD,
    PALETTE_ROW,
    PHONE_SEARCH,
    TAB_BAR,
    TAB_BAR_ADD,
    TAB_BAR_ITEM,
    TAB_BAR_ITEM_ACTIVE,
    TAB_BAR_SPACER,
    TOP_NAV,
    TOP_NAV_ITEM,
    TOP_NAV_ITEM_ACTIVE,
    TOP_NAV_MENU,
    TOP_NAV_SEARCH,
    apply_brand,
    theme_css,
)

try:
    _APP_VERSION = f"v{_pkg_version('kaleta')}"
except Exception:
    _APP_VERSION = "v0.1.0"

# Drawer geometry from the design handoff: 236px expanded, 64px collapsed.
_DRAWER_WIDTH = "width=236"
# An overlay at every width, closed until something opens it. With artboard
# `1e` the top bar is the desktop navigation, so a drawer standing open beside
# it would be the same 24 links twice — and a drawer Quasar considers
# "desktop" reserves 236px of page gutter whether or not you can see it.
_DRAWER_BREAKPOINT = "breakpoint=99999"

# Pinned entries rendered above the groups: (icon, path, label_key).
# See docs/ux/feature-categorization-audit.md (Phase A) for the rationale.
NAV_PINNED: list[tuple[str, str, str]] = [
    ("dashboard", "/", "nav.dashboard"),
    ("auto_awesome", "/wizard", "nav.wizard"),
]

# Paths matched exactly for active-state (their sub-pages have own nav entries).
_NAV_EXACT: frozenset[str] = frozenset({"/", "/wizard"})

# Groups collapsed on first visit; a user's stored choice always wins.
_DEFAULT_COLLAPSED: frozenset[str] = frozenset({"nav.group_setup"})

# Groups: (group_key, [(icon, path, label_key), ...]) — ordered by workflow
# cadence (capture → monthly → plans → insight → setup), mirroring the
# workflow map in docs/bdd.md.
NAV_GROUPS: list[tuple[str, list[tuple[str, str, str]]]] = [
    (
        "nav.group_capture",
        [
            ("receipt_long", "/transactions", "nav.transactions"),
            ("upload_file", "/import", "nav.import"),
        ],
    ),
    (
        "nav.group_monthly",
        [
            ("bar_chart", "/budgets", "nav.budgets"),
            ("calendar_month", "/payment-calendar", "nav.payment_calendar"),
            ("event_available", "/wizard/monthly-readiness", "nav.monthly_readiness"),
            ("subscriptions", "/wizard/subscriptions", "nav.subscriptions"),
        ],
    ),
    (
        "nav.group_plans",
        [
            ("edit_note", "/budget-plan", "nav.budget_plan"),
            ("savings", "/wizard/safety-funds", "nav.safety_funds"),
            ("handshake", "/wizard/personal-loans", "nav.personal_loans"),
        ],
    ),
    (
        "nav.group_insight",
        [
            ("assessment", "/reports", "nav.reports"),
            ("pie_chart", "/net-worth", "nav.net_worth"),
            ("insights", "/forecast", "nav.forecast"),
            ("credit_card", "/credit", "nav.credit"),
            ("calculate", "/credit-calculator", "nav.credit_calculator"),
        ],
    ),
    (
        "nav.group_setup",
        [
            ("account_balance_wallet", "/accounts", "nav.accounts"),
            ("account_balance", "/institutions", "nav.institutions"),
            ("category", "/categories", "nav.categories"),
            ("label", "/tags", "nav.tags"),
            ("person_search", "/payees", "nav.payees"),
            ("rule", "/rules", "nav.rules"),
            ("cleaning_services", "/housekeeping", "nav.housekeeping"),
            ("settings", "/settings", "nav.settings"),
        ],
    ),
]


# ── Top bar sections (artboard 1e) ────────────────────────────────────────────
# The five `NAV_GROUPS` keys, with a short label each: "Monthly cycle" and
# "Plans & funds" are names for a sidebar heading, not for a bar that has to
# fit five of them and a search field on one 60px line.
NAV_SECTIONS: list[tuple[str, str]] = [
    ("nav.group_capture", "nav.section_capture"),
    ("nav.group_monthly", "nav.section_monthly"),
    ("nav.group_plans", "nav.section_plans"),
    ("nav.group_insight", "nav.section_insight"),
    ("nav.group_setup", "nav.section_setup"),
]


def nav_destinations() -> list[tuple[str, str, str]]:
    """Every place the app can navigate to, as (icon, path, label_key).

    The palette's whole content, and the only list of routes that claims to
    be complete — the pinned pair first, then each group in bar order.
    """
    destinations = list(NAV_PINNED)
    groups = dict(NAV_GROUPS)
    for group_key, _label_key in NAV_SECTIONS:
        destinations.extend(groups.get(group_key, []))
    return destinations


# ── Bottom tab bar (artboard 1f) ──────────────────────────────────────────────
# Five tabs, the middle one an add button. The drawer stays — "More" is what
# opens it — because the long tail of setup pages does not fit five slots and
# never will. ``None`` as the path means the entry is not a route.
TAB_BAR_ENTRIES: list[tuple[str, str | None, str]] = [
    ("home", "/", "nav.tab_home"),
    ("receipt_long", "/transactions", "nav.tab_transactions"),
    # The dialog the Alt+N shortcut opens, reached the way that shortcut
    # reaches it from another page. There is no standalone quick-add dialog to
    # call into — ``quick_actions`` navigates here too.
    ("add", "/transactions?new=1", "nav.tab_add"),
    ("calendar_month", "/payment-calendar", "nav.tab_plan"),
    ("menu", None, "nav.tab_more"),
]


def nav_active(nav_path: str, current_path: str) -> bool:
    """Is *current_path* "at" *nav_path*?

    One rule for both nav surfaces: the drawer and the tab bar disagreeing
    about where you are is worse than either being wrong. Entries in
    ``_NAV_EXACT`` match exactly because their sub-pages have entries of
    their own; everything else claims its sub-paths.
    """
    if nav_path in _NAV_EXACT:
        return current_path == nav_path
    return current_path == nav_path or current_path.startswith(f"{nav_path}/")


def _tab_bar(drawer: ui.left_drawer, current_path: str) -> None:
    """The phone's navigation. Hidden above ``md`` by ``.k-tabbar``'s own rule.

    Buttons rather than links: an ``<a href>`` would give long-press and
    open-in-new-tab, at the cost of a full document load on every tap, and on
    a phone that is the difference the tab bar exists to remove. The active
    tab carries ``aria-current`` so the bar still says where you are.
    """
    with ui.element("nav").classes(TAB_BAR).props(f'aria-label="{t("nav.navigation")}"'):
        for icon, path, key in TAB_BAR_ENTRIES:
            is_add = key == "nav.tab_add"
            active = path is not None and not is_add and nav_active(path, current_path)
            item = (
                ui.element("button")
                .classes(f"{TAB_BAR_ITEM} {TAB_BAR_ITEM_ACTIVE if active else ''}".strip())
                .props(
                    f'data-tab="{key}" aria-label="{t(key)}"'
                    + (' aria-current="page"' if active else "")
                )
            )
            with item:
                if is_add:
                    with ui.element("div").classes(TAB_BAR_ADD):
                        ui.icon(icon, size="1.4rem")
                else:
                    ui.icon(icon, size="1.35rem")
                    ui.label(t(key))
            if path is None:
                item.on("click", lambda: drawer.toggle())
            else:
                item.on("click", lambda p=path: ui.navigate.to(p))


def _top_nav(current_path: str, open_palette: Callable[[], None]) -> None:
    """The desktop navigation: two pinned links, five section menus, a search.

    Hidden below the breakpoint by `.k-topnav`'s own rule, where the tab bar
    and the drawer take over — the same trap as `.k-tabbar`, and avoided the
    same way rather than with `hidden md:flex`.
    """
    groups = dict(NAV_GROUPS)
    with ui.row().classes(f"{TOP_NAV} items-center gap-1 min-w-0"):
        for icon, path, key in NAV_PINNED:
            active = nav_active(path, current_path)
            # `color=None`: Quasar's colour helpers are `!important`, so a
            # button that keeps NiceGUI's default `primary` cannot be given
            # the bar's own muted ink by any stylesheet rule.
            item = ui.button(
                t(key), icon=icon, on_click=lambda p=path: ui.navigate.to(p), color=None
            ).props("flat no-caps dense")
            item.classes(f"{TOP_NAV_ITEM} {TOP_NAV_ITEM_ACTIVE if active else ''}".strip())
            item.props["data-nav"] = key
            if active:
                item.props["aria-current"] = "page"

        for group_key, label_key in NAV_SECTIONS:
            items = groups.get(group_key, [])
            active = any(nav_active(path, current_path) for _icon, path, _key in items)
            # `icon-right=<name>` rather than `icon=`: Quasar's `icon` prop is
            # the left slot, and `icon-right` is a name, not a flag — passing
            # it as one put every chevron in front of its label.
            section = ui.button(t(label_key), color=None).props(
                "flat no-caps dense icon-right=expand_more"
            )
            section.classes(f"{TOP_NAV_ITEM} {TOP_NAV_ITEM_ACTIVE if active else ''}".strip())
            section.props["data-section"] = group_key
            if active:
                section.props["aria-current"] = "page"
            with section, ui.menu().props("auto-close").classes(TOP_NAV_MENU):
                for icon, path, key in items:
                    ui.menu_item(t(key), on_click=lambda p=path: ui.navigate.to(p)).props(
                        f'icon={icon} data-nav="{key}"'
                    )

    ui.space()
    ui.button(t("nav.palette_open"), icon="search", on_click=open_palette).props(
        "flat no-caps dense"
    ).classes(TOP_NAV_SEARCH).props("data-palette-open")


def _build_palette() -> Callable[[], None]:
    """⌘K. Returns the callable that opens it.

    Routes only — the long tail of pages that five sections cannot show at
    once. Deliberately not a search over transactions or payees: a palette
    that sometimes answers with data and sometimes with a page is a palette
    you have to read before you trust it.
    """
    destinations = nav_destinations()
    rows: list[tuple[ui.element, str]] = []

    with ui.dialog() as dialog, ui.card().classes(f"{PALETTE_CARD} w-[520px] max-w-[92vw] gap-0"):
        query = (
            ui.input(placeholder=t("nav.palette_placeholder"))
            .props("autofocus borderless dense clearable")
            .classes("w-full px-1")
        )
        listing = ui.column().classes("w-full gap-0 mt-2 max-h-[52vh] overflow-y-auto")
        empty = ui.label(t("nav.palette_empty")).classes(f"{BODY_MUTED} px-2 py-3")
        empty.set_visibility(False)

        with listing:
            for icon, path, key in destinations:
                row = ui.row().classes(f"{PALETTE_ROW} w-full items-center gap-3 cursor-pointer")
                row.props["data-palette-row"] = key
                row.on("click", lambda p=path: _go(dialog, p))
                with row:
                    ui.icon(icon, size="1.1rem").classes(MUTED)
                    ui.label(t(key)).classes("text-sm")
                rows.append((row, t(key).casefold()))

    def _filter() -> None:
        needle = (query.value or "").strip().casefold()
        shown = 0
        for row, label in rows:
            match = needle in label
            row.set_visibility(match)
            shown += match
        empty.set_visibility(shown == 0)

    def _first_match() -> str | None:
        needle = (query.value or "").strip().casefold()
        for (_row, label), (_icon, path, _key) in zip(rows, destinations, strict=True):
            if needle in label:
                return path
        return None

    query.on_value_change(lambda _e: _filter())
    query.on("keydown.enter", lambda: _go(dialog, _first_match()))

    def _open() -> None:
        query.set_value("")
        _filter()
        dialog.open()

    return _open


def _go(dialog: ui.dialog, path: str | None) -> None:
    if path is None:
        return
    dialog.close()
    ui.navigate.to(path)


@contextmanager
def page_layout(title: str, *, wide: bool = False, container: str | None = None) -> Generator[None]:
    """Shared layout: header + top nav + left drawer + main content area.

    ``title`` still names the page for the document and for callers; it left
    the header itself with artboard `1e`, where the active section says where
    you are and a 60px bar has five sections and a search to fit.

    ``container`` swaps the content column's classes — the dashboard asks for
    its own padding and band gap (``DASH_PAGE_CONTAINER``); every other page
    keeps ``PAGE_CONTAINER``.
    """
    from kaleta.config.setup_config import is_configured
    from kaleta.views.auto_post import maybe_auto_post_due

    ui.add_head_html(PWA_HEAD)
    ui.add_head_html(f"<style>{theme_css()}</style>")
    apply_brand()

    if not is_configured():
        ui.navigate.to("/setup")
        yield
        return

    # Session-start equivalent of auto-post (storage.user unavailable at process startup).
    ui.timer(0.01, maybe_auto_post_due, once=True)

    is_dark: bool = app.storage.user.get("dark_mode", False)

    dark_mode = ui.dark_mode(value=is_dark)
    drawer: Any
    toggle_btn: Any
    close_dialog: Any

    def toggle_dark() -> None:
        dark_mode.toggle()
        app.storage.user["dark_mode"] = dark_mode.value
        toggle_btn.props(f"icon={'light_mode' if dark_mode.value else 'dark_mode'}")

    ui.query("body").classes(PAGE_SHELL)

    current_path = ui.context.client.request.url.path if ui.context.client else "/"

    def _nav_active(nav_path: str) -> bool:
        return nav_active(nav_path, current_path)

    open_palette = _build_palette()

    with ui.header().classes(f"{HEADER} items-center px-4 gap-3 h-[60px]"):
        # The hamburger is the phone's, where the drawer is the long tail and
        # the tab bar's "More" opens the same thing. Above the breakpoint the
        # top bar is the navigation and a hamburger beside it is noise. The
        # mini toggle went with it: there is no docked drawer left to shrink,
        # and `sidebar_mini` is now read by nothing.
        with ui.row().classes(f"{DRAWER_CONTROLS} items-center gap-1"):
            ui.button(icon="menu", on_click=lambda: drawer.toggle()).props(
                "flat round dense color=primary"
            )
        ui.label("Kaleta").classes("k-heading text-[17px] font-semibold tracking-tight")
        _top_nav(current_path, open_palette)
        ui.space()
        ui.button(icon="search", on_click=open_palette).props(
            "flat round dense color=primary"
        ).classes(PHONE_SEARCH).tooltip(t("nav.palette_open"))
        toggle_btn = (
            ui.button(
                icon="light_mode" if is_dark else "dark_mode",
                on_click=toggle_dark,
            )
            .props("flat round dense color=primary")
            .tooltip(t("common.toggle_dark"))
        )

        session_username: str = app.storage.user.get("username", "")

        async def _logout() -> None:
            from kaleta.auth.session import logout_session
            from kaleta.services import AuthService, with_session

            name = session_username or None

            async def _record(session: Any) -> None:
                await AuthService(session).record_logout(username=name)

            await with_session(_record)
            logout_session()
            ui.navigate.to("/login")

        account_btn = ui.button(icon="account_circle").props("flat round dense color=primary")
        with account_btn, ui.menu():
            if session_username:
                ui.menu_item(session_username).props("disable")
            ui.menu_item(t("auth.logout"), on_click=_logout).props("icon=logout")

        async def _close_db() -> None:
            from kaleta.config.setup_config import clear_db
            from kaleta.services import dispose_sessions

            close_dialog.close()
            clear_db()
            await dispose_sessions()
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

    # No explicit value: NiceGUI then sets Quasar's `show-if-above`, which
    # opens the drawer on a desktop and leaves it shut on a phone. Forcing it
    # open (`value=True`) covered the whole page below the breakpoint, where
    # the drawer is an overlay and "More" in the tab bar is what opens it.
    #
    with ui.left_drawer().props(f"{_DRAWER_WIDTH} {_DRAWER_BREAKPOINT}").classes(DRAWER) as drawer:
        # Pinned entries — always visible, above the workflow groups.
        for icon, path, key in NAV_PINNED:
            active = _nav_active(path)
            item_cls = f"{NAV_ITEM} {NAV_ITEM_ACTIVE if active else ''}".strip()
            with ui.item(on_click=lambda p=path: ui.navigate.to(p)).classes(item_cls):
                with ui.item_section().props("avatar"):
                    ui.icon(icon)
                with ui.item_section():
                    ui.item_label(t(key))

        ui.separator().classes("mx-4 my-2 opacity-60")

        # Collapse state persisted per user across page loads
        nav_collapsed: dict[str, bool] = dict(app.storage.user.get("nav_collapsed", {}))

        for group_key, items in NAV_GROUPS:
            is_col = nav_collapsed.get(group_key, group_key in _DEFAULT_COLLAPSED)

            # Clickable group header
            with ui.row().classes(NAV_GROUP_ROW) as hdr:
                ui.label(t(group_key)).classes(NAV_GROUP)
                chevron = ui.icon(
                    "keyboard_arrow_down" if is_col else "keyboard_arrow_up", size="xs"
                ).classes("text-slate-400")

            # Items container — hidden when collapsed
            with ui.column().classes("w-full gap-0") as items_col:
                for icon, path, key in items:
                    active = _nav_active(path)
                    item_cls = f"{NAV_ITEM} {NAV_ITEM_ACTIVE if active else ''}".strip()
                    with ui.item(on_click=lambda p=path: ui.navigate.to(p)).classes(item_cls):
                        with ui.item_section().props("avatar"):
                            ui.icon(icon)
                        with ui.item_section():
                            ui.item_label(t(key))

            items_col.set_visibility(not is_col)

            # Toggle callback — captures loop vars via default args to avoid closure bug
            def _make_toggle(gk: str, col: ui.column, ch: ui.icon) -> Callable[[], None]:
                def _toggle() -> None:
                    stored: dict[str, bool] = dict(app.storage.user.get("nav_collapsed", {}))
                    now_col = not stored.get(gk, gk in _DEFAULT_COLLAPSED)
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
        ui.label(_APP_VERSION).classes("k-app-version k-mono text-xs text-center pb-3 w-full")

    # ── Keyboard shortcuts help dialog (press ?) ──────────────────────────
    with ui.dialog() as shortcuts_dialog, ui.card().classes("w-[480px] gap-3"):
        ui.label(t("common.shortcuts_help")).classes("text-lg font-bold")
        ui.label(t("common.shortcuts_global")).classes("text-sm font-semibold text-slate-500 mt-2")
        with ui.grid(columns=2).classes("w-full gap-x-8 gap-y-1"):
            ui.label("Alt+N").classes(f"k-mono {INK} text-sm font-semibold")
            ui.label(t("common.shortcut_new_tx")).classes("text-sm")
            ui.label("?").classes(f"k-mono {INK} text-sm font-semibold")
            ui.label(t("common.shortcut_open_help")).classes("text-sm")
        ui.label(t("common.shortcuts_transactions")).classes(
            "text-sm font-semibold text-slate-500 mt-3"
        )
        with ui.grid(columns=2).classes("w-full gap-x-8 gap-y-1"):
            ui.label("Enter").classes(f"k-mono {INK} text-sm font-semibold")
            ui.label(t("common.shortcut_submit")).classes("text-sm")
            ui.label("Escape").classes(f"k-mono {INK} text-sm font-semibold")
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
        if key in ("k", "K") and (
            getattr(e.modifiers, "meta", False) or getattr(e.modifiers, "ctrl", False)
        ):
            # ⌘K on a Mac, Ctrl+K elsewhere. The browser only claims ⌘K while
            # the address bar has focus, so a page-level handler is safe here.
            open_palette()
        elif key == "?" and no_mod:
            shortcuts_dialog.open()
        elif key == "n" and alt_only:
            is_tx_page = await ui.run_javascript("window.location.pathname === '/transactions'")
            if not is_tx_page:
                ui.navigate.to("/transactions?new=1")

    ui.keyboard(on_key=_global_key, active=True)

    _tab_bar(drawer, current_path)

    width_cls = "max-w-screen-2xl" if wide else "max-w-7xl"
    with ui.column().classes(f"{container or PAGE_CONTAINER} {width_cls}"):
        if settings.demo and not app.storage.user.get("demo_banner_dismissed", False):

            def _dismiss_demo_banner() -> None:
                app.storage.user["demo_banner_dismissed"] = True
                demo_banner.set_visibility(False)

            with ui.row().classes(
                "k-info-banner w-full items-center gap-2 px-3 py-2 mb-3 rounded"
            ) as demo_banner:
                ui.icon("info", size="sm")
                ui.label(t("common.demo_banner")).classes("text-sm flex-grow")
                ui.button(
                    icon="close",
                    on_click=_dismiss_demo_banner,
                ).props("flat dense round").tooltip(t("common.demo_dismiss"))
        yield
        # Room for the tab bar, which is fixed over the foot of the page and
        # would otherwise sit on the last card. `display:none` above the
        # breakpoint — a zero-height child still costs the column a gap.
        ui.element("div").classes(TAB_BAR_SPACER)
