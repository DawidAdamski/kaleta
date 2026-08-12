# SPDX-License-Identifier: AGPL-3.0-or-later
"""Account coverage panel and recent import history on the Import page."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from nicegui import ui

from kaleta.i18n import t
from kaleta.schemas.account import AccountActivityResponse
from kaleta.services.account_service import STALE_ACTIVITY_DAYS, AccountService
from kaleta.views.theme import BODY_MUTED, SECTION_CARD


def _fmt_date(value: date | None) -> str:
    return value.isoformat() if value is not None else "—"


def _fmt_datetime(value: object | None) -> str:
    if value is None:
        return "—"
    # ImportRun.created_at is timezone-aware datetime
    iso = getattr(value, "isoformat", None)
    if callable(iso):
        text = str(iso())
        return text[:16].replace("T", " ")
    return "—"


def _coverage_sort_key(row: AccountActivityResponse) -> tuple[int, date, str]:
    """Unloaded / never-imported first, then oldest activity, then name."""
    newest = row.newest_transaction_date
    if newest is None:
        return (0, date.min, row.name.lower())
    return (1, newest, row.name.lower())


@dataclass
class CoverageSection:
    container: ui.column

    def render(
        self,
        rows: list[AccountActivityResponse],
        *,
        recent_runs: list[tuple[str, str, str, int, int]] | None = None,
    ) -> None:
        """Render coverage table and optional recent-imports list.

        ``recent_runs`` items are ``(when, filename, account_name, imported, skipped)``.
        """
        self.container.clear()
        sorted_rows = sorted(rows, key=_coverage_sort_key)
        with self.container:
            with ui.card().classes(f"{SECTION_CARD} w-full"):
                ui.label(t("import.coverage_heading")).classes("text-lg font-medium")
                ui.label(t("import.coverage_hint")).classes(f"{BODY_MUTED} text-sm mb-2")

                with ui.row().classes(
                    "w-full px-2 py-1 text-xs text-slate-500 font-medium border-b gap-2"
                ):
                    ui.label(t("common.name")).classes("flex-1")
                    ui.label(t("import.coverage_last_activity")).classes("w-36")
                    ui.label(t("import.coverage_last_import")).classes("flex-1")

                if not sorted_rows:
                    ui.label(t("accounts.no_accounts")).classes(f"{BODY_MUTED} text-sm py-2")
                else:
                    for row in sorted_rows:
                        stale = AccountService.is_stale(row.newest_transaction_date)
                        with ui.row().classes("w-full px-2 py-2 items-center border-b gap-2"):
                            with ui.row().classes("flex-1 items-center gap-2 min-w-0"):
                                ui.label(row.name).classes("font-medium truncate")
                                if stale:
                                    ui.badge(t("import.coverage_stale")).props(
                                        "outline color=orange dense"
                                    ).tooltip(
                                        t(
                                            "import.coverage_stale_hint",
                                            days=STALE_ACTIVITY_DAYS,
                                        )
                                    )
                            ui.label(_fmt_date(row.newest_transaction_date)).classes(
                                "w-36 text-sm font-mono"
                            )
                            if row.last_import_filename:
                                ui.label(
                                    t(
                                        "import.coverage_last_import_value",
                                        filename=row.last_import_filename,
                                        when=_fmt_datetime(row.last_import_at),
                                    )
                                ).classes("flex-1 text-sm truncate")
                            else:
                                ui.label(t("import.coverage_never")).classes(
                                    "flex-1 text-sm text-slate-500"
                                )

            with ui.expansion(t("import.history_heading"), icon="history").classes(
                f"{SECTION_CARD} w-full mt-2"
            ):
                if not recent_runs:
                    ui.label(t("import.history_empty")).classes(f"{BODY_MUTED} text-sm")
                else:
                    for when, filename, account_name, imported, skipped in recent_runs:
                        ui.label(
                            t(
                                "import.history_row",
                                when=when,
                                filename=filename,
                                account=account_name,
                                imported=imported,
                                skipped=skipped,
                            )
                        ).classes("text-sm py-1")


def build_coverage_section() -> CoverageSection:
    with ui.column().classes("w-full gap-0") as container:
        pass
    return CoverageSection(container=container)
