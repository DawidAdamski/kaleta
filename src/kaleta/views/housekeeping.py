# SPDX-License-Identifier: AGPL-3.0-or-later
"""Housekeeping page — surface duplicate candidates and offer one-click merge."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from nicegui import app, ui

from kaleta.i18n import t
from kaleta.services import DedupeService, IntegrityService, with_session
from kaleta.services.dedupe_service import (
    CategoryGroup,
    PayeeGroup,
    PayeeGroupItem,
    TxGroup,
)
from kaleta.services.integrity_service import ForeignKeyViolation
from kaleta.services.payee_merge_service import (
    AutoMergeEntry,
    MergeProposal,
    PayeeMergeService,
)
from kaleta.views.components.payee_merge import (
    MergeAction,
    MergeConfirmDialog,
    PayeeMergeSuggestion,
)
from kaleta.views.error_handling import handle_kaleta_error
from kaleta.views.layout import page_layout
from kaleta.views.settings.user_prefs import get_payee_dedupe_max_distance
from kaleta.views.theme import (
    AMOUNT_EXPENSE,
    AMOUNT_INCOME,
    BODY_MUTED,
    PAGE_TITLE,
    SECTION_CARD,
    SECTION_HEADING,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def register() -> None:
    @ui.page("/housekeeping")
    async def housekeeping_page() -> None:
        dup_window_days = int(app.storage.user.get("housekeeping_duplicate_days", 0) or 0) or None
        payee_max_distance = get_payee_dedupe_max_distance()

        async def _load(
            session: AsyncSession,
        ) -> tuple[
            list[TxGroup],
            list[PayeeGroup],
            list[MergeProposal],
            list[AutoMergeEntry],
            list[CategoryGroup],
        ]:
            svc = DedupeService(session)
            merge_svc = PayeeMergeService(session)
            payee_groups = await svc.similar_payees(payee_max_distance=payee_max_distance)
            return (
                await svc.duplicate_transactions(window_days=dup_window_days),
                payee_groups,
                await merge_svc.propose_merges(
                    grouped=[[item.id for item in g.items] for g in payee_groups]
                ),
                await merge_svc.recent_auto_merges(),
                await svc.redundant_categories(),
            )

        (
            tx_groups,
            payee_groups,
            proposals,
            recent_merges,
            category_groups,
        ) = await with_session(_load)

        with page_layout(t("housekeeping.title"), wide=True):
            # ── Header ───────────────────────────────────────────────────
            with ui.column().classes("gap-1"):
                ui.label(t("housekeeping.title")).classes(PAGE_TITLE)
                ui.label(t("housekeeping.subtitle")).classes(BODY_MUTED)

            # ── Shared confirm dialog ────────────────────────────────────
            confirm = MergeConfirmDialog(on_done=ui.navigate.reload)

            # ── Duplicate transactions ───────────────────────────────────
            _render_tx_section(tx_groups, confirm.ask)

            # ── Similar payees ───────────────────────────────────────────
            _render_payee_section(payee_groups, proposals, confirm.ask)

            # ── Recently auto-merged payees (undo window) ─────────────────
            _render_recent_merges_section(recent_merges)

            # ── Redundant categories ─────────────────────────────────────
            _render_category_section(category_groups, confirm.ask)

            # ── Integrity (SQLite FK check) ───────────────────────────────
            _render_integrity_section()


# ── Sections ─────────────────────────────────────────────────────────────────


def _section_header(title_key: str, hint_key: str, count: int) -> None:
    with ui.row().classes("w-full items-center gap-3"):
        ui.label(t(title_key)).classes(SECTION_HEADING)
        if count > 0:
            ui.badge(t("housekeeping.group_count", count=count)).props("color=amber-7 rounded")
    ui.label(t(hint_key)).classes(BODY_MUTED)


def _render_integrity_section() -> None:
    with ui.card().classes(SECTION_CARD):
        ui.label(t("housekeeping.integrity_heading")).classes(SECTION_HEADING)
        ui.label(t("housekeeping.integrity_hint")).classes(BODY_MUTED)

        result_box = ui.column().classes("w-full gap-2 mt-2")
        with result_box:
            ui.label(t("housekeeping.integrity_idle")).classes(BODY_MUTED)

        async def _run_check() -> None:
            async def _load(session: Any) -> tuple[bool, list[ForeignKeyViolation]]:
                svc = IntegrityService(session)
                if not await svc.is_sqlite():
                    return False, []
                return True, await svc.foreign_key_check()

            try:
                is_sqlite, violations = await with_session(_load)
            except Exception as exc:
                if handle_kaleta_error(exc):
                    return
                raise

            result_box.clear()
            with result_box:
                if not is_sqlite:
                    ui.label(t("housekeeping.integrity_not_sqlite")).classes(BODY_MUTED)
                    return
                if not violations:
                    ui.label(t("housekeeping.integrity_ok")).classes(
                        "text-sm text-positive font-medium"
                    )
                    return
                ui.badge(t("housekeeping.integrity_violation_count", count=len(violations))).props(
                    "color=negative rounded"
                )
                for v in violations:
                    ui.label(
                        t(
                            "housekeeping.integrity_violation_row",
                            table=v.table,
                            rowid=v.rowid,
                            parent=v.parent,
                        )
                    ).classes("text-sm")

        ui.button(
            t("housekeeping.integrity_run"),
            icon="verified",
            on_click=_run_check,
        ).props("color=primary unelevated size=sm outline").classes("mt-2")


def _render_tx_section(groups: list[TxGroup], ask_confirm: Any) -> None:
    with ui.card().classes(SECTION_CARD):
        _section_header(
            "housekeeping.transactions_heading",
            "housekeeping.transactions_hint",
            len(groups),
        )
        if not groups:
            ui.label(t("housekeeping.transactions_empty")).classes(f"{BODY_MUTED} mt-2")
            return
        for g in groups:
            _render_tx_group(g, ask_confirm)


def _render_payee_section(
    groups: list[PayeeGroup],
    proposals: list[MergeProposal],
    ask_confirm: Callable[[int, MergeAction], None],
) -> None:
    with ui.card().classes(SECTION_CARD):
        _section_header(
            "housekeeping.payees_heading",
            "housekeeping.payees_hint",
            len(groups) + len(proposals),
        )
        if not groups and not proposals:
            ui.label(t("housekeeping.payees_empty")).classes(f"{BODY_MUTED} mt-2")
            return
        for g in groups:
            PayeeMergeSuggestion(g, ask_confirm)
        for proposal in proposals:
            _render_proposal(proposal, ask_confirm)


def _render_proposal(
    proposal: MergeProposal, ask_confirm: Callable[[int, MergeAction], None]
) -> None:
    group = PayeeGroup(
        items=(
            PayeeGroupItem(proposal.left_id, proposal.left_name, proposal.left_tx_count),
            PayeeGroupItem(proposal.right_id, proposal.right_name, proposal.right_tx_count),
        )
    )

    async def _dismiss() -> None:
        async def _run(session: AsyncSession) -> None:
            await PayeeMergeService(session).dismiss(proposal.left_id, proposal.right_id)

        await with_session(_run)
        ui.notify(t("housekeeping.proposal_dismissed"), type="positive")
        ui.navigate.reload()

    PayeeMergeSuggestion(
        group,
        ask_confirm,
        keeper_id=proposal.left_id,
        caption=t(
            "housekeeping.proposal_caption",
            score=f"{proposal.score:.0%}",
            reason=t(f"housekeeping.proposal_reason_{proposal.reason.value}"),
        ),
        on_dismiss=_dismiss,
    )


def _render_recent_merges_section(entries: list[AutoMergeEntry]) -> None:
    if not entries:
        return
    with ui.card().classes(SECTION_CARD).props("data-recent-merges"):
        ui.label(t("housekeeping.recent_merges_heading")).classes(SECTION_HEADING)
        ui.label(t("housekeeping.recent_merges_hint")).classes(BODY_MUTED)
        for entry in entries:
            with ui.row().classes("w-full items-center gap-3 py-1"):
                ui.label(
                    t(
                        "housekeeping.recent_merge_row",
                        merged=entry.merged_name,
                        keeper=entry.keeper_name,
                        score=f"{entry.score:.0%}",
                    )
                ).classes("flex-1 text-sm")
                ui.label(entry.merged_at.date().isoformat()).classes("text-xs text-slate-500")

                async def _undo(_e: object = None, record_id: int = entry.id) -> None:
                    async def _run(session: AsyncSession) -> None:
                        await PayeeMergeService(session).undo(record_id)

                    try:
                        await with_session(_run)
                    except Exception as exc:
                        if handle_kaleta_error(exc):
                            return
                        raise
                    ui.notify(t("housekeeping.recent_merge_undone"), type="positive")
                    ui.navigate.reload()

                ui.button(t("housekeeping.recent_merge_undo"), icon="undo", on_click=_undo).props(
                    "flat size=sm color=primary"
                )


def _render_category_section(groups: list[CategoryGroup], ask_confirm: Any) -> None:
    with ui.card().classes(SECTION_CARD):
        _section_header(
            "housekeeping.categories_heading",
            "housekeeping.categories_hint",
            len(groups),
        )
        if not groups:
            ui.label(t("housekeeping.categories_empty")).classes(f"{BODY_MUTED} mt-2")
            return
        for g in groups:
            _render_category_group(g, ask_confirm)


# ── Group renderers ──────────────────────────────────────────────────────────


def _render_tx_group(group: TxGroup, ask_confirm: Any) -> None:
    # Default keeper = oldest date. User can change.
    keeper_holder = {"id": group.items[0].id}
    keeper_options: dict[int, str] = {
        item.id: f"#{item.id} · {item.date} · {item.description[:40] or '—'}"
        for item in group.items
    }

    with ui.element("div").classes("w-full mt-3 p-3 rounded border border-slate-200/30"):
        for item in group.items:
            with ui.row().classes("w-full items-center gap-3 py-1"):
                ui.label(str(item.date)).classes("w-24 text-xs text-slate-500")
                ui.label(item.description[:60] or "—").classes("flex-1 text-sm")
                amount_cls = AMOUNT_INCOME if item.amount >= 0 else AMOUNT_EXPENSE
                ui.label(f"{item.amount:,.2f}").classes(f"{amount_cls} w-24 text-right text-sm")
                ui.label(f"#{item.id}").classes("w-16 text-xs text-slate-500 text-right")

        with ui.row().classes("w-full items-center gap-3 mt-2"):
            keeper_sel = (
                ui.select(
                    options=keeper_options,
                    label=t("housekeeping.keeper_label"),
                    value=keeper_holder["id"],
                )
                .props("dense outlined")
                .classes("flex-1")
            )

            def _on_change(_e: object = None, holder: dict[str, int] = keeper_holder) -> None:
                if keeper_sel.value is not None:
                    holder["id"] = int(keeper_sel.value)

            keeper_sel.on("update:model-value", _on_change)

            async def _merge() -> None:
                keeper_id = keeper_holder["id"]
                other_ids = [item.id for item in group.items if item.id != keeper_id]

                async def _run(session: Any) -> int:
                    return await DedupeService(session).merge_transactions(
                        keeper_id=keeper_id, other_ids=other_ids
                    )

                deleted = await with_session(_run)
                ui.notify(t("housekeeping.merged_tx", count=deleted), type="positive")

            delete_count = len(group.items) - 1
            ui.button(
                t("housekeeping.merge"),
                icon="merge_type",
                on_click=lambda _e, a=_merge, c=delete_count: ask_confirm(c, a),
            ).props("color=primary unelevated size=sm")


def _render_category_group(group: CategoryGroup, ask_confirm: Any) -> None:
    default_keeper = max(group.items, key=lambda x: (x.transaction_count, -x.id))
    keeper_holder = {"id": default_keeper.id}
    keeper_options: dict[int, str] = {
        item.id: f"{item.name} ({item.transaction_count})" for item in group.items
    }

    with ui.element("div").classes("w-full mt-3 p-3 rounded border border-slate-200/30"):
        for item in group.items:
            with ui.row().classes("w-full items-center gap-3 py-1"):
                ui.label(item.name).classes("flex-1 text-sm")
                ui.label(t("housekeeping.transaction_count", count=item.transaction_count)).classes(
                    "text-xs text-slate-500 w-32 text-right"
                )

        with ui.row().classes("w-full items-center gap-3 mt-2"):
            keeper_sel = (
                ui.select(
                    options=keeper_options,
                    label=t("housekeeping.keeper_label"),
                    value=keeper_holder["id"],
                )
                .props("dense outlined")
                .classes("flex-1")
            )

            def _on_change(_e: object = None, holder: dict[str, int] = keeper_holder) -> None:
                if keeper_sel.value is not None:
                    holder["id"] = int(keeper_sel.value)

            keeper_sel.on("update:model-value", _on_change)

            async def _merge() -> None:
                keeper_id = keeper_holder["id"]
                other_ids = [item.id for item in group.items if item.id != keeper_id]

                async def _run(session: Any) -> int:
                    return await DedupeService(session).merge_categories(
                        keeper_id=keeper_id, other_ids=other_ids
                    )

                merged = await with_session(_run)
                ui.notify(
                    t("housekeeping.merged_categories", count=merged),
                    type="positive",
                )

            delete_count = len(group.items) - 1
            ui.button(
                t("housekeeping.merge"),
                icon="merge_type",
                on_click=lambda _e, a=_merge, c=delete_count: ask_confirm(c, a),
            ).props("color=primary unelevated size=sm")
