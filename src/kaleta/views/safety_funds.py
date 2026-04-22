from __future__ import annotations

from decimal import Decimal
from typing import Any

from nicegui import ui

from kaleta.db import AsyncSessionFactory
from kaleta.i18n import t
from kaleta.models.reserve_fund import ReserveFundBackingMode, ReserveFundKind
from kaleta.schemas.reserve_fund import (
    ReserveFundCreate,
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
            funds = await ReserveFundService(session).list_with_progress()

        account_opts: dict[int, str] = {a.id: a.name for a in accounts}

        with page_layout(t("safety_funds.title"), wide=True):
            # ── Header ───────────────────────────────────────────────────
            with ui.row().classes("w-full items-center justify-between gap-4 flex-wrap"):
                with ui.column().classes("gap-1"):
                    ui.label(t("safety_funds.title")).classes(PAGE_TITLE)
                    ui.label(t("safety_funds.subtitle")).classes(BODY_MUTED)
                add_btn = ui.button(
                    t("safety_funds.add"), icon="add"
                ).props("color=primary unelevated size=md")

            # ── Add/Edit dialog ──────────────────────────────────────────
            dialog_state: dict[str, Any] = {
                "name": "",
                "kind": ReserveFundKind.EMERGENCY,
                "target": Decimal("0"),
                "account_id": next(iter(account_opts), None),
                "multiplier": 3,
            }

            with ui.dialog() as add_dialog, ui.card().classes("w-[520px] gap-3"):
                ui.label(t("safety_funds.dialog_title")).classes("text-lg font-bold")

                kind_in = ui.select(
                    options={
                        ReserveFundKind.EMERGENCY.value: t("safety_funds.kind_emergency"),
                        ReserveFundKind.IRREGULAR.value: t("safety_funds.kind_irregular"),
                        ReserveFundKind.VACATION.value: t("safety_funds.kind_vacation"),
                    },
                    label=t("safety_funds.kind"),
                    value=ReserveFundKind.EMERGENCY.value,
                ).props("dense outlined").classes("w-full")

                name_in = ui.input(
                    label=t("safety_funds.name"),
                    value=t("safety_funds.default_name_emergency"),
                ).props("dense outlined").classes("w-full")

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
                    account_in = ui.select(
                        options=account_opts,
                        label=t("safety_funds.backing_account"),
                        value=dialog_state["account_id"],
                        with_input=True,
                    ).props("dense outlined").classes("w-full")
                else:
                    account_in = None
                    ui.label(t("safety_funds.need_account")).classes(
                        f"{BODY_MUTED} text-amber-7"
                    )

                def _on_kind_change(e: Any) -> None:
                    # Show multiplier only for emergency; update default name
                    is_emergency = e.args == ReserveFundKind.EMERGENCY.value
                    multiplier_row.set_visibility(is_emergency)
                    defaults = {
                        ReserveFundKind.EMERGENCY.value: t(
                            "safety_funds.default_name_emergency"
                        ),
                        ReserveFundKind.IRREGULAR.value: t(
                            "safety_funds.default_name_irregular"
                        ),
                        ReserveFundKind.VACATION.value: t(
                            "safety_funds.default_name_vacation"
                        ),
                    }
                    name_in.set_value(defaults[e.args])

                kind_in.on("update:model-value", _on_kind_change)

                with ui.row().classes("w-full justify-end gap-2 mt-2"):
                    ui.button(t("common.cancel"), on_click=add_dialog.close).props("flat")
                    save_btn = ui.button(
                        t("common.save"), icon="check"
                    ).props("color=primary unelevated")

            async def _save_fund() -> None:
                if account_in is None or account_in.value is None:
                    ui.notify(t("safety_funds.need_account"), type="warning")
                    return
                try:
                    kind = ReserveFundKind(kind_in.value)
                    payload = ReserveFundCreate(
                        name=(name_in.value or "").strip()
                        or t("safety_funds.default_name_emergency"),
                        kind=kind,
                        target_amount=Decimal(str(target_in.value or 0)),
                        backing_mode=ReserveFundBackingMode.ACCOUNT,
                        backing_account_id=int(account_in.value),
                        emergency_multiplier=(
                            int(multiplier_in.value or 3)
                            if kind == ReserveFundKind.EMERGENCY
                            else None
                        ),
                    )
                except Exception as exc:  # pragma: no cover — defensive
                    ui.notify(str(exc), type="negative")
                    return

                async with AsyncSessionFactory() as s:
                    await ReserveFundService(s).create(payload)
                add_dialog.close()
                ui.notify(t("safety_funds.saved"), type="positive")
                ui.navigate.reload()

            save_btn.on_click(_save_fund)

            def _open_add_dialog() -> None:
                if not account_opts:
                    ui.notify(t("safety_funds.need_account"), type="warning")
                    return
                multiplier_row.set_visibility(True)
                add_dialog.open()

            add_btn.on_click(_open_add_dialog)

            # ── Fund cards ───────────────────────────────────────────────
            if not funds:
                with (
                    ui.card().classes(SECTION_CARD),
                    ui.row().classes("w-full items-center gap-3"),
                ):
                    ui.icon("savings", size="1.8rem").classes("text-slate-400")
                    with ui.column().classes("gap-0.5"):
                        ui.label(t("safety_funds.empty_heading")).classes(SECTION_HEADING)
                        ui.label(t("safety_funds.empty_body")).classes(BODY_MUTED)

            for f in funds:
                _render_fund_card(f, account_opts)


def _render_fund_card(
    fund: ReserveFundWithProgress, account_opts: dict[int, str]
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
            with ui.column().classes("items-end gap-0"):
                ui.label(
                    f"{_fmt_amount(fund.current_balance)} / {_fmt_amount(fund.target_amount)}"
                ).classes("text-base font-semibold")
                pct_label = int(round(float(fund.progress_pct) * 100))
                ui.label(f"{pct_label}%").classes(f"text-sm text-{colour}")

        ui.linear_progress(
            value=pct_clamped, size="8px", show_value=False, color=colour
        ).classes("w-full mt-3")

        with ui.row().classes("w-full items-center justify-between mt-2 text-xs"):
            ui.label(
                t("safety_funds.backed_by", account=account_name)
            ).classes(BODY_MUTED)
            if (
                fund.kind == ReserveFundKind.EMERGENCY
                and fund.months_of_coverage is not None
            ):
                ui.label(
                    t(
                        "safety_funds.months_of_coverage",
                        months=f"{fund.months_of_coverage:.1f}",
                    )
                ).classes(BODY_MUTED)
