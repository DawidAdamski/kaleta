from __future__ import annotations

from decimal import Decimal
from typing import Any

from nicegui import ui

from kaleta.db import AsyncSessionFactory
from kaleta.i18n import t
from kaleta.models.reserve_fund import ReserveFundBackingMode, ReserveFundKind
from kaleta.schemas.reserve_fund import (
    ReserveFundCreate,
    ReserveFundUpdate,
    ReserveFundWithProgress,
)
from kaleta.services import AccountService, ReserveFundService
from kaleta.views.layout import page_layout
from kaleta.views.theme import (
    BODY_MUTED,
    PAGE_TITLE,
    SECTION_CARD,
    SECTION_HEADING,
)

_KIND_ICONS: dict[ReserveFundKind, str] = {
    ReserveFundKind.EMERGENCY: "local_fire_department",
    ReserveFundKind.IRREGULAR: "build_circle",
    ReserveFundKind.VACATION: "beach_access",
}


def _fmt_amount(d: Decimal) -> str:
    return f"{d:,.2f}"


def _progress_color(pct: Decimal) -> str:
    """Return a Quasar colour token for the progress bar."""
    if pct >= Decimal("1"):
        return "positive"
    if pct >= Decimal("0.5"):
        return "amber-7"
    return "negative"


def register() -> None:
    @ui.page("/wizard/safety-funds")
    async def safety_funds_page() -> None:
        async with AsyncSessionFactory() as session:
            accounts = await AccountService(session).list()
            svc = ReserveFundService(session)
            active_funds = await svc.list_with_progress(include_archived=False)
            all_funds = await svc.list_with_progress(include_archived=True)

        archived_funds = [f for f in all_funds if f.is_archived]
        account_opts: dict[int, str] = {a.id: a.name for a in accounts}

        with page_layout(t("safety_funds.title"), wide=True):
            # ── Header ───────────────────────────────────────────────────
            with ui.row().classes("w-full items-center justify-between gap-4 flex-wrap"):
                with ui.column().classes("gap-1"):
                    ui.label(t("safety_funds.title")).classes(PAGE_TITLE)
                    ui.label(t("safety_funds.subtitle")).classes(BODY_MUTED)
                add_btn = ui.button(t("safety_funds.add"), icon="add").props(
                    "color=primary unelevated size=md"
                )

            # ── Add/Edit dialog ──────────────────────────────────────────
            editing_state: dict[str, int | None] = {"id": None}

            with ui.dialog() as fund_dialog, ui.card().classes("w-[520px] gap-3"):
                dialog_title = ui.label(t("safety_funds.dialog_title")).classes("text-lg font-bold")

                kind_in = (
                    ui.select(
                        options={
                            ReserveFundKind.EMERGENCY.value: t("safety_funds.kind_emergency"),
                            ReserveFundKind.IRREGULAR.value: t("safety_funds.kind_irregular"),
                            ReserveFundKind.VACATION.value: t("safety_funds.kind_vacation"),
                        },
                        label=t("safety_funds.kind"),
                        value=ReserveFundKind.EMERGENCY.value,
                    )
                    .props("dense outlined")
                    .classes("w-full")
                )

                name_in = (
                    ui.input(
                        label=t("safety_funds.name"),
                        value=t("safety_funds.default_name_emergency"),
                    )
                    .props("dense outlined")
                    .classes("w-full")
                )

                multiplier_row = ui.row().classes("w-full items-center gap-2")
                with multiplier_row:
                    ui.label(t("safety_funds.multiplier")).classes("text-sm text-slate-500")
                    multiplier_in = (
                        ui.number(value=3, min=1, max=24, format="%d")
                        .props("dense outlined")
                        .classes("flex-1")
                    )
                    ui.label(t("safety_funds.multiplier_unit")).classes(BODY_MUTED)

                target_in = (
                    ui.number(
                        label=t("safety_funds.target"),
                        value=0,
                        min=0,
                        format="%.2f",
                    )
                    .props("dense outlined")
                    .classes("w-full")
                )

                if account_opts:
                    account_in = (
                        ui.select(
                            options=account_opts,
                            label=t("safety_funds.backing_account"),
                            value=next(iter(account_opts)),
                            with_input=True,
                        )
                        .props("dense outlined")
                        .classes("w-full")
                    )
                else:
                    account_in = None
                    ui.label(t("safety_funds.need_account")).classes(f"{BODY_MUTED} text-amber-7")

                def _on_kind_change(e: Any) -> None:
                    # Show multiplier only for emergency; update default name
                    # only when creating a new fund (don't clobber user edits).
                    is_emergency = e.args == ReserveFundKind.EMERGENCY.value
                    multiplier_row.set_visibility(is_emergency)
                    if editing_state["id"] is None:
                        defaults = {
                            ReserveFundKind.EMERGENCY.value: t(
                                "safety_funds.default_name_emergency"
                            ),
                            ReserveFundKind.IRREGULAR.value: t(
                                "safety_funds.default_name_irregular"
                            ),
                            ReserveFundKind.VACATION.value: t("safety_funds.default_name_vacation"),
                        }
                        name_in.set_value(defaults[e.args])

                kind_in.on("update:model-value", _on_kind_change)

                with ui.row().classes("w-full justify-end gap-2 mt-2"):
                    ui.button(t("common.cancel"), on_click=fund_dialog.close).props("flat")
                    save_btn = ui.button(t("common.save"), icon="check").props(
                        "color=primary unelevated"
                    )

            async def _save_fund() -> None:
                if account_in is None or account_in.value is None:
                    ui.notify(t("safety_funds.need_account"), type="warning")
                    return
                try:
                    kind = ReserveFundKind(kind_in.value)
                    name = (name_in.value or "").strip() or t(
                        f"safety_funds.default_name_{kind.value}"
                    )
                    target = Decimal(str(target_in.value or 0))
                    account_id = int(account_in.value)
                    multiplier = (
                        int(multiplier_in.value or 3) if kind == ReserveFundKind.EMERGENCY else None
                    )
                except Exception as exc:  # pragma: no cover — defensive
                    ui.notify(str(exc), type="negative")
                    return

                async with AsyncSessionFactory() as s:
                    fund_svc = ReserveFundService(s)
                    if editing_state["id"] is None:
                        try:
                            payload = ReserveFundCreate(
                                name=name,
                                kind=kind,
                                target_amount=target,
                                backing_mode=ReserveFundBackingMode.ACCOUNT,
                                backing_account_id=account_id,
                                emergency_multiplier=multiplier,
                            )
                        except Exception as exc:  # pragma: no cover — defensive
                            ui.notify(str(exc), type="negative")
                            return
                        await fund_svc.create(payload)
                    else:
                        await fund_svc.update(
                            editing_state["id"],
                            ReserveFundUpdate(
                                name=name,
                                kind=kind,
                                target_amount=target,
                                backing_account_id=account_id,
                                emergency_multiplier=multiplier,
                            ),
                        )
                fund_dialog.close()
                ui.notify(t("safety_funds.saved"), type="positive")
                ui.navigate.reload()

            save_btn.on_click(_save_fund)

            def _open_add_dialog() -> None:
                if not account_opts:
                    ui.notify(t("safety_funds.need_account"), type="warning")
                    return
                editing_state["id"] = None
                dialog_title.set_text(t("safety_funds.dialog_title"))
                kind_in.set_value(ReserveFundKind.EMERGENCY.value)
                name_in.set_value(t("safety_funds.default_name_emergency"))
                target_in.set_value(0)
                multiplier_in.set_value(3)
                multiplier_row.set_visibility(True)
                if account_in is not None and account_opts:
                    account_in.set_value(next(iter(account_opts)))
                fund_dialog.open()

            add_btn.on_click(_open_add_dialog)

            def _open_edit_dialog(fund: ReserveFundWithProgress) -> None:
                editing_state["id"] = fund.id
                dialog_title.set_text(t("safety_funds.dialog_edit_title"))
                kind_in.set_value(fund.kind.value)
                name_in.set_value(fund.name)
                target_in.set_value(float(fund.target_amount))
                multiplier_in.set_value(fund.emergency_multiplier or 3)
                multiplier_row.set_visibility(fund.kind == ReserveFundKind.EMERGENCY)
                if (
                    account_in is not None
                    and fund.backing_account_id is not None
                    and fund.backing_account_id in account_opts
                ):
                    account_in.set_value(fund.backing_account_id)
                fund_dialog.open()

            # ── Delete confirmation dialog ───────────────────────────────
            pending_delete: dict[str, int | str] = {"id": 0, "name": ""}

            with ui.dialog() as delete_dialog, ui.card().classes("w-[440px] gap-3"):
                ui.label(t("safety_funds.confirm_delete_title")).classes("text-lg font-bold")
                delete_body = ui.label("").classes(BODY_MUTED)
                with ui.row().classes("w-full justify-end gap-2 mt-2"):
                    ui.button(t("common.cancel"), on_click=delete_dialog.close).props("flat")
                    confirm_delete_btn = ui.button(
                        t("safety_funds.confirm_delete_confirm"), icon="delete"
                    ).props("color=negative unelevated")

            async def _confirm_delete() -> None:
                fund_id = int(pending_delete["id"])
                async with AsyncSessionFactory() as s:
                    await ReserveFundService(s).delete(fund_id)
                delete_dialog.close()
                ui.notify(t("safety_funds.deleted"), type="positive")
                ui.navigate.reload()

            confirm_delete_btn.on_click(_confirm_delete)

            def _open_delete_dialog(fund: ReserveFundWithProgress) -> None:
                pending_delete["id"] = fund.id
                pending_delete["name"] = fund.name
                delete_body.set_text(t("safety_funds.confirm_delete_body", name=fund.name))
                delete_dialog.open()

            async def _archive_fund(fund_id: int) -> None:
                async with AsyncSessionFactory() as s:
                    await ReserveFundService(s).archive(fund_id)
                ui.notify(t("safety_funds.archived_msg"), type="positive")
                ui.navigate.reload()

            async def _unarchive_fund(fund_id: int) -> None:
                async with AsyncSessionFactory() as s:
                    await ReserveFundService(s).unarchive(fund_id)
                ui.notify(t("safety_funds.unarchived_msg"), type="positive")
                ui.navigate.reload()

            # ── Active funds ─────────────────────────────────────────────
            if not active_funds:
                with (
                    ui.card().classes(SECTION_CARD),
                    ui.row().classes("w-full items-center gap-3"),
                ):
                    ui.icon("savings", size="1.8rem").classes("text-slate-400")
                    with ui.column().classes("gap-0.5"):
                        ui.label(t("safety_funds.empty_heading")).classes(SECTION_HEADING)
                        ui.label(t("safety_funds.empty_body")).classes(BODY_MUTED)

            for f in active_funds:
                _render_fund_card(
                    f,
                    account_opts,
                    on_edit=_open_edit_dialog,
                    on_archive=_archive_fund,
                    on_delete=_open_delete_dialog,
                )

            # ── Archived funds ───────────────────────────────────────────
            if archived_funds:
                with (
                    ui.expansion(
                        t("safety_funds.archived_section_heading"),
                        icon="archive",
                    )
                    .classes("w-full mt-4")
                    .props("dense")
                ):
                    ui.label(t("safety_funds.archived_section_body")).classes(
                        f"{BODY_MUTED} text-xs mb-2"
                    )
                    for f in archived_funds:
                        _render_archived_card(
                            f,
                            account_opts,
                            on_unarchive=_unarchive_fund,
                            on_delete=_open_delete_dialog,
                        )


def _render_fund_card(
    fund: ReserveFundWithProgress,
    account_opts: dict[int, str],
    *,
    on_edit: Any,
    on_archive: Any,
    on_delete: Any,
) -> None:
    pct_clamped = min(float(fund.progress_pct), 1.0)
    colour = _progress_color(fund.progress_pct)
    account_name = (
        account_opts.get(fund.backing_account_id, "—")
        if fund.backing_account_id is not None
        else "—"
    )

    with ui.card().classes(SECTION_CARD):
        with ui.row().classes("w-full items-center justify-between gap-3"):
            with ui.row().classes("items-center gap-3"):
                ui.icon(_KIND_ICONS[fund.kind], size="1.6rem").classes("text-primary")
                with ui.column().classes("gap-0"):
                    ui.label(fund.name).classes("text-lg font-semibold")
                    ui.label(t(f"safety_funds.kind_{fund.kind.value}")).classes(BODY_MUTED)
            with ui.row().classes("items-center gap-1"):
                with ui.column().classes("items-end gap-0 mr-2"):
                    ui.label(
                        f"{_fmt_amount(fund.current_balance)} / {_fmt_amount(fund.target_amount)}"
                    ).classes("text-base font-semibold")
                    pct_label = int(round(float(fund.progress_pct) * 100))
                    ui.label(f"{pct_label}%").classes(f"text-sm text-{colour}")
                ui.button(icon="edit", on_click=lambda _e, f=fund: on_edit(f)).props(
                    "flat dense round color=grey-7"
                ).tooltip(t("safety_funds.edit"))
                ui.button(
                    icon="archive",
                    on_click=lambda _e, fid=fund.id: on_archive(fid),
                ).props("flat dense round color=grey-7").tooltip(t("safety_funds.archive"))
                ui.button(
                    icon="delete",
                    on_click=lambda _e, f=fund: on_delete(f),
                ).props("flat dense round color=negative").tooltip(t("safety_funds.delete"))

        # Progress bar — for emergency funds with a multiplier >= 2 we overlay
        # tick marks so each segment represents one "month of survival money"
        # (= target ÷ multiplier). For all other funds it's a plain bar.
        show_ticks = (
            fund.kind == ReserveFundKind.EMERGENCY
            and fund.emergency_multiplier is not None
            and fund.emergency_multiplier >= 2
        )
        if show_ticks:
            # Slightly taller container so ticks stick out above and below the
            # 8px track — that way a single hard edge reads against green,
            # amber, red fills and the unfilled grey rail alike.
            with ui.element("div").classes("relative w-full mt-3 h-4 flex items-center"):
                ui.linear_progress(
                    value=pct_clamped, size="8px", show_value=False, color=colour
                ).classes("w-full")
                # Full-height dark ticks with a 2px width and a faint white
                # shadow. mypy/narrowing: show_ticks guard ensures multiplier.
                multiplier = fund.emergency_multiplier or 0
                for i in range(1, multiplier):
                    pct = int(round(i * 100 / multiplier))
                    ui.element("div").classes(
                        "absolute top-0 bottom-0 w-0.5 bg-slate-900/70 "
                        "[box-shadow:0_0_0_1px_rgba(255,255,255,0.35)] "
                        "-translate-x-1/2"
                    ).style(f"left: {pct}%;")
        else:
            ui.linear_progress(
                value=pct_clamped, size="8px", show_value=False, color=colour
            ).classes("w-full mt-3")

        with ui.row().classes("w-full items-center justify-between mt-2 text-xs"):
            ui.label(t("safety_funds.backed_by", account=account_name)).classes(BODY_MUTED)
            # Survival-months footer: only for emergency funds with a multiplier
            # and a non-zero target (required for the per-chunk math).
            if (
                fund.kind == ReserveFundKind.EMERGENCY
                and fund.emergency_multiplier is not None
                and fund.emergency_multiplier >= 1
                and fund.target_amount > 0
            ):
                chunk = fund.target_amount / Decimal(fund.emergency_multiplier)
                survived = (fund.current_balance / chunk).quantize(Decimal("0.1"))
                ui.label(
                    t(
                        "safety_funds.survival_months",
                        months=f"{survived:.1f}",
                        goal=fund.emergency_multiplier,
                    )
                ).classes(BODY_MUTED)
            elif fund.kind == ReserveFundKind.EMERGENCY and fund.months_of_coverage is not None:
                # Legacy fallback: emergency fund without a multiplier still
                # gets the old trailing-spend line so the card isn't empty.
                months_txt = f"{fund.months_of_coverage:.1f}"
                if fund.emergency_multiplier is not None:
                    label_text = t(
                        "safety_funds.months_of_coverage_goal",
                        months=months_txt,
                        goal=fund.emergency_multiplier,
                    )
                else:
                    label_text = t(
                        "safety_funds.months_of_coverage",
                        months=months_txt,
                    )
                ui.label(label_text).classes(BODY_MUTED)


def _render_archived_card(
    fund: ReserveFundWithProgress,
    account_opts: dict[int, str],
    *,
    on_unarchive: Any,
    on_delete: Any,
) -> None:
    account_name = (
        account_opts.get(fund.backing_account_id, "—")
        if fund.backing_account_id is not None
        else "—"
    )
    with (
        ui.card().classes(f"{SECTION_CARD} opacity-75"),
        ui.row().classes("w-full items-center justify-between gap-3"),
    ):
        with ui.row().classes("items-center gap-3"):
            ui.icon(_KIND_ICONS[fund.kind], size="1.3rem").classes("text-slate-400")
            with ui.column().classes("gap-0"):
                ui.label(fund.name).classes("text-base font-medium")
                ui.label(t("safety_funds.backed_by", account=account_name)).classes(
                    f"{BODY_MUTED} text-xs"
                )
        with ui.row().classes("items-center gap-1"):
            ui.label(_fmt_amount(fund.target_amount)).classes(f"{BODY_MUTED} text-sm mr-2")
            ui.button(
                icon="unarchive",
                on_click=lambda _e, fid=fund.id: on_unarchive(fid),
            ).props("flat dense round color=primary").tooltip(t("safety_funds.unarchive"))
            ui.button(
                icon="delete",
                on_click=lambda _e, f=fund: on_delete(f),
            ).props("flat dense round color=negative").tooltip(t("safety_funds.delete"))
