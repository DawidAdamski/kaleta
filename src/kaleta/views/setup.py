"""First-run setup page — lets the user choose a local or cloud database."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from pathlib import Path

from nicegui import ui

from kaleta.i18n import t
from kaleta.pwa import PWA_HEAD

# ── helpers ──────────────────────────────────────────────────────────────────


def _sqlite_url(file_path: str) -> str:
    return f"sqlite+aiosqlite:///{file_path}"


async def _run_migrations(db_url: str) -> None:
    """Run Alembic migrations in a thread-pool executor (synchronous Alembic API)."""
    from alembic.config import Config

    from alembic import command

    alembic_ini = Path(__file__).parents[3] / "alembic.ini"

    def _upgrade() -> None:
        os.environ["KALETA_MIGRATE_URL"] = db_url
        try:
            cfg = Config(str(alembic_ini))
            command.upgrade(cfg, "head")
        finally:
            os.environ.pop("KALETA_MIGRATE_URL", None)

    await asyncio.get_event_loop().run_in_executor(None, _upgrade)


async def _activate_db(db_url: str, name: str, spinner: ui.spinner, status: ui.label) -> None:
    """Run migrations → configure proxy → save config → navigate home."""
    from kaleta.config import settings
    from kaleta.config.setup_config import save_db
    from kaleta.db import configure_database

    try:
        status.set_text(t("setup.migrating"))
        await _run_migrations(db_url)

        configure_database(db_url, debug=settings.debug)
        save_db(db_url, name=name)

        status.set_text(t("setup.success"))
        await asyncio.sleep(0.6)
        ui.navigate.to("/")
    except Exception as exc:
        spinner.set_visibility(False)
        ui.notify(f"{t('setup.error')}: {exc}", type="negative")
        status.set_text("")


# ── file/folder picker ────────────────────────────────────────────────────────


def _make_picker(
    target_input: ui.input,
    mode: str = "file",  # "file" | "folder"
) -> tuple[ui.dialog, Callable[[], None]]:
    """Build a dialog-based file/folder browser.

    Returns (dialog, open_fn) — call open_fn() to show the dialog.
    """
    state: dict[str, Path] = {"cwd": Path.home()}

    def _pick_folder() -> None:
        target_input.set_value(str(state["cwd"]))
        dialog.close()

    with ui.dialog() as dialog, ui.card().classes("w-full max-w-xl p-0 overflow-hidden"):
        # Header: current path
        cwd_label = ui.label("").classes("text-xs font-mono px-4 py-2 bg-grey-2 w-full truncate")

        # Scrollable file list
        with ui.scroll_area().classes("w-full h-72"):
            entries_col = ui.column().classes("w-full gap-0")

        # Footer
        with ui.row().classes("px-4 py-3 justify-end gap-2 border-t"):
            if mode == "folder":
                ui.button(
                    t("setup.select_folder"),
                    icon="check",
                    on_click=_pick_folder,
                ).props("color=primary unelevated")
            ui.button(t("common.cancel"), on_click=dialog.close).props("flat")

    def _refresh() -> None:
        cwd = state["cwd"]
        cwd_label.set_text(str(cwd))
        entries_col.clear()

        with entries_col:
            # ".." parent row
            if cwd != cwd.parent:
                with (
                    ui.row()
                    .classes("items-center gap-2 px-4 py-2 w-full cursor-pointer hover:bg-grey-1")
                    .on("click", lambda: _go_up())
                ):
                    ui.icon("arrow_upward", size="1.2rem").classes("text-grey-5")
                    ui.label("..").classes("text-sm text-grey-6")

            try:
                entries = sorted(
                    cwd.iterdir(),
                    key=lambda p: (not p.is_dir(), p.name.lower()),
                )
            except PermissionError:
                ui.label(t("setup.picker_no_access")).classes("text-sm text-negative p-4")
                return

            for p in entries:
                if p.name.startswith("."):
                    continue
                if p.is_dir():
                    with (
                        ui.row()
                        .classes(
                            "items-center gap-2 px-4 py-2 w-full cursor-pointer hover:bg-grey-1"
                        )
                        .on("click", lambda p=p: _enter(p))
                    ):
                        ui.icon("folder", size="1.2rem").classes("text-amber-6")
                        ui.label(p.name).classes("text-sm")
                elif mode == "file" and p.suffix == ".db":
                    with (
                        ui.row()
                        .classes(
                            "items-center gap-2 px-4 py-2 w-full cursor-pointer"
                            " hover:bg-primary-1 font-medium"
                        )
                        .on("click", lambda p=p: _pick_file(p))
                    ):
                        ui.icon("storage", size="1.2rem").classes("text-primary")
                        ui.label(p.name).classes("text-sm")

    def _go_up() -> None:
        state["cwd"] = state["cwd"].parent
        _refresh()

    def _enter(p: Path) -> None:
        state["cwd"] = p
        _refresh()

    def _pick_file(p: Path) -> None:
        target_input.set_value(str(p))
        dialog.close()

    def open_picker() -> None:
        _refresh()
        dialog.open()

    return dialog, open_picker


# ── recent list (module-level, called at page-build time) ─────────────────────


def _render_recent() -> None:
    from kaleta.config.setup_config import get_recent

    recent = get_recent()
    if not recent:
        ui.label(t("setup.no_recent")).classes("text-sm text-grey-5 py-6 text-center w-full")
        return

    for entry in recent:
        row = ui.row().classes(
            "w-full items-center gap-3 px-3 py-2 rounded-lg cursor-pointer hover:bg-grey-2"
        )
        with row:
            ui.icon("storage", size="1.4rem").classes("text-primary")
            with ui.column().classes("flex-1 gap-0"):
                ui.label(entry.get("name") or entry["url"]).classes("font-medium text-sm")
                ui.label(entry["url"]).classes("text-xs text-grey-5")
            ui.icon("chevron_right").classes("text-grey-4")

        # async handler keeps NiceGUI client context
        async def _handle_pick(e: dict[str, str] = entry) -> None:
            spinner = ui.spinner(size="sm")
            status = ui.label("").classes("text-sm text-grey-6")
            await _activate_db(e["url"], name=e.get("name", ""), spinner=spinner, status=status)

        row.on("click", _handle_pick)


# ── page ─────────────────────────────────────────────────────────────────────


def register() -> None:  # noqa: PLR0915
    @ui.page("/setup")
    async def setup_page() -> None:  # noqa: PLR0915
        ui.add_head_html(PWA_HEAD)
        with ui.column().classes("w-full min-h-screen items-center justify-center p-8 gap-6"):
            # logo
            with ui.row().classes("items-center gap-3"):
                ui.icon("account_balance_wallet", size="3rem").classes("text-primary")
                ui.label("Kaleta").classes("text-4xl font-bold")

            ui.label(t("setup.welcome")).classes("text-lg text-grey-6 text-center max-w-lg")

            # ── Step 1: Local vs Cloud ──
            with ui.column().classes("w-full max-w-2xl gap-4") as step_choose:
                ui.label(t("setup.choose_storage")).classes("text-xl font-semibold text-center")

                with ui.row().classes("w-full gap-4 justify-center"):
                    with (
                        (
                            ui.card()
                            .classes("flex-1 cursor-pointer hover:shadow-lg transition-shadow p-6")
                            .on("click", lambda: _go_local())
                        ),
                        ui.column().classes("items-center gap-3 text-center"),
                    ):
                        ui.icon("storage", size="3rem").classes("text-primary")
                        ui.label(t("setup.local_title")).classes("text-lg font-semibold")
                        ui.label(t("setup.local_desc")).classes("text-sm text-grey-6")
                        ui.badge(t("setup.recommended"), color="primary").classes("mt-2")

                    with (
                        ui.card().classes("flex-1 p-6 opacity-60"),
                        ui.column().classes("items-center gap-3 text-center"),
                    ):
                        ui.icon("cloud", size="3rem").classes("text-grey-5")
                        ui.label(t("setup.cloud_title")).classes("text-lg font-semibold")
                        ui.label(t("setup.cloud_desc")).classes("text-sm text-grey-6")
                        ui.badge(t("setup.coming_soon"), color="grey").classes("mt-2")

            # ── Step 2: Local options ──
            with ui.column().classes("w-full max-w-2xl gap-4") as step_local:
                step_local.set_visibility(False)

                with ui.row().classes("items-center gap-2"):
                    ui.button(icon="arrow_back", on_click=lambda: _back_to_choose()).props(
                        "flat round dense"
                    )
                    ui.label(t("setup.local_title")).classes("text-xl font-semibold")

                with ui.tabs().classes("w-full") as tabs:
                    ui.tab("new", label=t("setup.tab_new"), icon="add_circle")
                    ui.tab("open", label=t("setup.tab_open"), icon="folder_open")
                    ui.tab("recent", label=t("setup.tab_recent"), icon="history")

                with ui.tab_panels(tabs, value="new").classes("w-full"):
                    # ── New database ──
                    with ui.tab_panel("new"):  # noqa: SIM117
                        with ui.card().classes("w-full p-6"):
                            with ui.column().classes("w-full gap-4"):
                                ui.label(t("setup.new_desc")).classes("text-sm text-grey-6")

                                new_name = ui.input(
                                    t("setup.db_name"),
                                    value=t("setup.db_name_default"),
                                    placeholder=t("setup.db_name_default"),
                                ).classes("w-full")

                                default_folder = str(Path.home() / "Documents")
                                with ui.row().classes("w-full items-center gap-1"):
                                    new_folder = ui.input(
                                        t("setup.db_location"),
                                        value=default_folder,
                                    ).classes("flex-1")
                                    _, open_folder_picker = _make_picker(new_folder, mode="folder")
                                    ui.button(
                                        icon="folder_open",
                                        on_click=lambda: open_folder_picker(),
                                    ).props("flat round dense").tooltip(t("setup.browse"))

                                with ui.row().classes("items-center gap-2"):
                                    new_spinner = ui.spinner(size="sm")
                                    new_spinner.set_visibility(False)
                                    new_status = ui.label("").classes("text-sm text-grey-6")

                                async def _handle_create() -> None:
                                    name = new_name.value.strip() or "kaleta"
                                    safe = "".join(
                                        c if c.isalnum() or c in "-_" else "_" for c in name.lower()
                                    )
                                    db_file = str(Path(new_folder.value) / f"{safe}.db")
                                    new_spinner.set_visibility(True)
                                    await _activate_db(
                                        _sqlite_url(db_file),
                                        name=name,
                                        spinner=new_spinner,
                                        status=new_status,
                                    )

                                ui.button(
                                    t("setup.create_btn"),
                                    icon="rocket_launch",
                                    on_click=_handle_create,
                                ).props("color=primary unelevated").classes("w-full")

                    # ── Open existing ──
                    with ui.tab_panel("open"):  # noqa: SIM117
                        with ui.card().classes("w-full p-6"):
                            with ui.column().classes("w-full gap-4"):
                                ui.label(t("setup.open_desc")).classes("text-sm text-grey-6")

                                with ui.row().classes("w-full items-center gap-1"):
                                    open_path = ui.input(
                                        t("setup.db_path"),
                                        placeholder=str(Path.home() / "Documents" / "budget.db"),
                                    ).classes("flex-1")
                                    _, open_file_picker = _make_picker(open_path, mode="file")
                                    ui.button(
                                        icon="folder_open",
                                        on_click=lambda: open_file_picker(),
                                    ).props("flat round dense").tooltip(t("setup.browse"))

                                with ui.row().classes("items-center gap-2"):
                                    open_spinner = ui.spinner(size="sm")
                                    open_spinner.set_visibility(False)
                                    open_status = ui.label("").classes("text-sm text-grey-6")

                                async def _handle_open() -> None:
                                    path = open_path.value.strip()
                                    if not path:
                                        ui.notify(t("setup.error_path_empty"), type="warning")
                                        return
                                    open_spinner.set_visibility(True)
                                    await _activate_db(
                                        _sqlite_url(path),
                                        name=Path(path).stem,
                                        spinner=open_spinner,
                                        status=open_status,
                                    )

                                ui.button(
                                    t("setup.open_btn"),
                                    icon="folder_open",
                                    on_click=_handle_open,
                                ).props("color=primary unelevated").classes("w-full")

                    # ── Recent ──
                    with ui.tab_panel("recent"):  # noqa: SIM117
                        with ui.card().classes("w-full p-4"):
                            _render_recent()

            # step transitions
            def _go_local() -> None:
                step_choose.set_visibility(False)
                step_local.set_visibility(True)

            def _back_to_choose() -> None:
                step_local.set_visibility(False)
                step_choose.set_visibility(True)
