# SPDX-License-Identifier: AGPL-3.0-or-later
import re
from collections.abc import Callable, Generator
from contextlib import contextmanager
from importlib.metadata import version as _pkg_version
from typing import Any

from nicegui import app, ui

from kaleta.config import settings
from kaleta.i18n import t
from kaleta.pwa import PWA_HEAD
from kaleta.views.theme import (
    AVATAR,
    BODY_MUTED,
    DRAWER,
    DRAWER_CONTROLS,
    HEADER,
    HEADER_DIVIDER,
    HEADER_ICON,
    HEADER_PAGE,
    HEADER_SEARCH,
    INK,
    MINI_TOGGLE,
    MUTED,
    NAV_GROUP,
    NAV_GROUP_ROW,
    NAV_ITEM,
    NAV_ITEM_ACTIVE,
    NAV_ITEM_PINNED,
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
    WORDMARK,
    apply_brand,
    theme_css,
)

try:
    _APP_VERSION = f"v{_pkg_version('kaleta')}"
except Exception:
    _APP_VERSION = "v0.1.0"

# Drawer geometry from artboards `1c` (236px, the dashboard) and `2a` (64px
# mini, the working screens).
_DRAWER_WIDTH = "width=236"
# The drawer stops being furniture and becomes an overlay at the same width
# the tab bar appears at — Quasar would otherwise hand over at 1023px, and a
# window 768-1023px wide would get neither a docked drawer nor a tab bar.
_DRAWER_BREAKPOINT = "breakpoint=767"
_MINI_PROPS = "mini mini-to-overlay mini-width=64"
_MINI_PROPS_OFF = "mini mini-to-overlay mini-width"

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


def nav_destinations() -> list[tuple[str, str, str]]:
    """Every place the app can navigate to, as (icon, path, label_key).

    The palette's whole content, and the only list of routes that claims to
    be complete — the pinned pair first, then each group in drawer order.
    """
    destinations = list(NAV_PINNED)
    for _group_key, items in NAV_GROUPS:
        destinations.extend(items)
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
        """The path Enter opens, or ``None`` while nothing has been typed.

        An empty needle is in every label, so without this guard a stray
        Enter on a freshly opened palette leaves the page for whatever
        happens to be first.
        """
        needle = (query.value or "").strip().casefold()
        if not needle:
            return None
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


def _initials(username: str) -> str:
    r"""Up to two letters for the header's avatar disc, as the artboards draw it.

    A single account name, not a person's two — so "demo" reads "DE" and
    "dawid.adamski" reads "DA": the first letter of each of the first two
    word-ish parts, upper-cased. An empty name falls back to the app's own
    letter rather than an empty disc.

    ``[\W_]+`` rather than ``[^0-9A-Za-z]+``: ``\W`` is unicode-aware, and
    this is a Polish app — an ASCII class reads "Łukasz" as a separator
    followed by "ukasz" and puts "UK" on the disc.
    """
    parts = [part for part in re.split(r"[\W_]+", username, flags=re.UNICODE) if part]
    if not parts:
        return "K"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[1][0]).upper()


def _go(dialog: ui.dialog, path: str | None) -> None:
    if path is None:
        return
    dialog.close()
    ui.navigate.to(path)


#: ⌘K / Ctrl+K, handled in the document rather than by ``ui.keyboard``.
#:
#: Two reasons, both of which ``ui.keyboard`` cannot answer. Chrome and
#: Firefox claim **Ctrl+K** for their own search box, and NiceGUI's keyboard
#: component never calls ``preventDefault`` — so the palette opened while the
#: focus jumped to the omnibox and the typing went there. And
#: ``ui.keyboard`` ignores ``input``/``textarea``/``select``/``button`` by
#: default, which is right for ``?`` and wrong for this: a search field is
#: exactly where "take me to another page" gets asked.
#:
#: The listener clicks the header's own palette button rather than reaching
#: for the server: the button is already bound to ``open_palette``, and a
#: programmatic click works whether or not the button is on screen — on a
#: phone it is hidden by ``.k-header-search``'s breakpoint.
_PALETTE_KEY_JS = """
<script>
document.addEventListener('keydown', (e) => {
  if ((e.metaKey || e.ctrlKey) && !e.altKey && (e.key === 'k' || e.key === 'K')) {
    e.preventDefault();
    const btn = document.querySelector('[data-palette-open]');
    if (btn) btn.click();
  }
}, true);
</script>
"""


@contextmanager
def page_layout(title: str, *, wide: bool = False, container: str | None = None) -> Generator[None]:
    """Shared layout: header + left drawer + main content area.

    ``title`` names the page twice, the way artboards `1c` and `2a` draw it:
    on the browser tab, and in the header after the wordmark and its hairline.

    ``container`` swaps the content column's classes — the dashboard asks for
    its own padding and grid gap (``DASH_PAGE_CONTAINER``); every other page
    keeps ``PAGE_CONTAINER``.
    """
    from kaleta.config.setup_config import is_configured
    from kaleta.views.auto_post import maybe_auto_post_due

    # Imported here, not at module scope: the report dialog reaches back into
    # views.settings for the user's preferences, which imports this module.
    from kaleta.views.bug_report_dialog import install_bug_report_dialog, open_bug_report_dialog
    from kaleta.views.error_handling import install_error_tray

    ui.page_title(f"{title} · Kaleta")
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
    is_mini: bool = app.storage.user.get("sidebar_mini", False)

    dark_mode = ui.dark_mode(value=is_dark)
    # Forward declarations for the closures below, which are defined before
    # the elements they reach for. Named types rather than `Any`: these are
    # ordinary NiceGUI classes and there is nothing to erase.
    drawer: ui.left_drawer
    toggle_btn: ui.button
    mini_btn: ui.button
    close_dialog: ui.dialog

    def toggle_dark() -> None:
        dark_mode.toggle()
        app.storage.user["dark_mode"] = dark_mode.value
        toggle_btn.props(f"icon={'light_mode' if dark_mode.value else 'dark_mode'}")

    def toggle_mini() -> None:
        new_mini = not app.storage.user.get("sidebar_mini", False)
        app.storage.user["sidebar_mini"] = new_mini
        if new_mini:
            drawer.props(_MINI_PROPS)
        else:
            drawer.props(remove=_MINI_PROPS_OFF)
        mini_btn.props(f"icon={'chevron_right' if new_mini else 'chevron_left'}")

    ui.query("body").classes(PAGE_SHELL)

    current_path = ui.context.client.request.url.path if ui.context.client else "/"

    def _nav_active(nav_path: str) -> bool:
        return nav_active(nav_path, current_path)

    open_palette = _build_palette()

    session_username: str = app.storage.user.get("username", "")

    with ui.header().classes(f"{HEADER} items-center px-6 h-[60px]"):
        # The hamburger is the phone's, where the drawer is an overlay and
        # the tab bar's "More" opens the same thing. Above the breakpoint the
        # drawer is docked and the mini toggle beside the page name is what
        # shrinks it to the 64px rail artboard `2a` draws.
        with ui.row().classes(f"{DRAWER_CONTROLS} items-center gap-1"):
            ui.button(icon="menu", on_click=lambda: drawer.toggle()).props(
                "flat round dense color=primary"
            )
        ui.label("Kaleta").classes(f"{WORDMARK} k-heading text-[17px] font-semibold tracking-tight")
        ui.element("span").classes(HEADER_DIVIDER)
        ui.label(title).classes(HEADER_PAGE)
        mini_btn = (
            ui.button(
                icon="chevron_right" if is_mini else "chevron_left",
                on_click=toggle_mini,
                color=None,
            )
            .props("flat round dense data-drawer-mini-toggle")
            .classes(f"{MINI_TOGGLE} {HEADER_ICON}")
            .tooltip(t("common.toggle_sidebar"))
        )
        ui.space()
        # The artboard labels this pill "Search transactions, payees…". What
        # is behind it is the ⌘K palette, which finds routes — so it keeps the
        # honest label until a data search exists to put there.
        ui.button(t("nav.palette_open"), icon="search", on_click=open_palette, color=None).props(
            "flat no-caps dense data-palette-open"
        ).classes(HEADER_SEARCH)
        ui.button(icon="search", on_click=open_palette).props(
            "flat round dense color=primary"
        ).classes(PHONE_SEARCH).tooltip(t("nav.palette_open"))
        toggle_btn = (
            ui.button(
                icon="light_mode" if is_dark else "dark_mode",
                on_click=toggle_dark,
                color=None,
            )
            .props("flat round dense")
            .classes(HEADER_ICON)
            .tooltip(t("common.toggle_dark"))
        )

        async def _logout() -> None:
            from kaleta.auth.session import logout_session
            from kaleta.services import AuthService, with_session

            name = session_username or None

            async def _record(session: Any) -> None:
                await AuthService(session).record_logout(username=name)

            await with_session(_record)
            logout_session()
            ui.navigate.to("/login")

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

        # The artboards end the header with a 28px initials disc and nothing
        # else, so the two controls that used to sit beside it — logout and
        # "close database" — moved into the menu it already dropped.
        account_btn = (
            ui.button(_initials(session_username), color=None)
            .props("flat dense no-caps")
            .classes(AVATAR)
            .tooltip(session_username or t("auth.logout"))
        )
        with account_btn, ui.menu():
            if session_username:
                ui.menu_item(session_username).props("disable")
            ui.menu_item(
                t("bugreport.menu_item"),
                on_click=open_bug_report_dialog,
            ).props("icon=bug_report")
            ui.menu_item(t("auth.logout"), on_click=_logout).props("icon=logout")
            ui.menu_item(t("common.close_db"), on_click=close_dialog.open).props("icon=eject")

    # No explicit value: NiceGUI then sets Quasar's `show-if-above`, which
    # opens the drawer on a desktop and leaves it shut on a phone. Forcing it
    # open (`value=True`) covered the whole page below the breakpoint, where
    # the drawer is an overlay and "More" in the tab bar is what opens it.
    with ui.left_drawer().props(f"{_DRAWER_WIDTH} {_DRAWER_BREAKPOINT}").classes(DRAWER) as drawer:
        if is_mini:
            drawer.props(_MINI_PROPS)
        # Pinned entries — always visible, above the workflow groups. No rule
        # under them: artboard `1c` separates them from the first group with
        # the group's own eyebrow padding, not with a line.
        for icon, path, key in NAV_PINNED:
            active = _nav_active(path)
            item_cls = f"{NAV_ITEM} {NAV_ITEM_PINNED} {NAV_ITEM_ACTIVE if active else ''}".strip()
            with ui.item(on_click=lambda p=path: ui.navigate.to(p)).classes(item_cls):
                with ui.item_section().props("avatar"):
                    ui.icon(icon)
                with ui.item_section():
                    ui.item_label(t(key))

        # Collapse state persisted per user across page loads
        nav_collapsed: dict[str, bool] = dict(app.storage.user.get("nav_collapsed", {}))

        for group_key, items in NAV_GROUPS:
            is_col = nav_collapsed.get(group_key, group_key in _DEFAULT_COLLAPSED)

            # Clickable group header
            with ui.row().classes(NAV_GROUP_ROW) as hdr:
                ui.label(t(group_key)).classes(NAV_GROUP)
                chevron = ui.icon(
                    "keyboard_arrow_down" if is_col else "keyboard_arrow_up", size="xs"
                ).classes(MUTED)

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

        # The artboard's index ends at Setup; the app has one more route to
        # offer and no group to put it in, so it keeps a hairline of its own.
        ui.separator().classes("mx-6 mt-4 mb-1 opacity-60")
        with ui.item(on_click=lambda: ui.navigate.to("/api-docs", new_tab=True)).classes(NAV_ITEM):
            with ui.item_section().props("avatar"):
                ui.icon("api")
            with ui.item_section():
                ui.item_label(t("nav.api_docs"))

        ui.space()
        # Left-aligned under the index, in mono, where artboard `1c` puts it.
        ui.label(_APP_VERSION).classes("k-app-version k-mono w-full")

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
        if key == "?" and no_mod:
            shortcuts_dialog.open()
        elif key == "n" and alt_only:
            is_tx_page = await ui.run_javascript("window.location.pathname === '/transactions'")
            if not is_tx_page:
                ui.navigate.to("/transactions?new=1")

    ui.keyboard(on_key=_global_key, active=True)
    ui.add_head_html(_PALETTE_KEY_JS)

    _tab_bar(drawer, current_path)

    # One per page: the tray a failure shows itself in, and the dialog its
    # Report button opens. Both are fixed/overlay, so placement is free.
    install_error_tray()
    install_bug_report_dialog()

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
