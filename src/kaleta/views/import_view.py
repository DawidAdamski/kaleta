from __future__ import annotations

from nicegui import events, ui

from kaleta.db import AsyncSessionFactory
from kaleta.i18n import t
from kaleta.services import AccountService, CategoryService, TransactionService
from kaleta.services.import_service import ImportResult, ImportService, ParsedRow
from kaleta.views.layout import page_layout


def register() -> None:
    @ui.page("/import")
    async def import_page() -> None:
        async with AsyncSessionFactory() as session:
            accounts    = await AccountService(session).list()
            categories  = await CategoryService(session).list()

        account_options  = {a.id: a.name for a in accounts}
        expense_cat_opts = {c.id: c.name for c in categories if c.type.value == "expense"}
        income_cat_opts  = {c.id: c.name for c in categories if c.type.value == "income"}

        # State
        parsed_result: list[ParsedRow] = []
        preview_rows: list[dict] = []

        with page_layout(t("import_csv.title")):
            ui.label(t("import_csv.title")).classes("text-2xl font-bold")

            # ── Step 1: settings ────────────────────────────────────────────
            with ui.card().classes("w-full"):
                ui.label(t("import_csv.step1")).classes("text-lg font-semibold mb-2")
                with ui.row().classes("w-full gap-4 flex-wrap"):
                    account_sel = ui.select(
                        account_options, label=t("import_csv.target_account")
                    ).classes("flex-1 min-w-48")
                    if account_options:
                        account_sel.value = next(iter(account_options))
                    expense_cat_sel = ui.select(
                        expense_cat_opts, label=t("import_csv.default_expense_cat")
                    ).classes("flex-1 min-w-48")
                    income_cat_sel = ui.select(
                        income_cat_opts, label=t("import_csv.default_income_cat")
                    ).classes("flex-1 min-w-48")

            # ── Step 2: upload ───────────────────────────────────────────────
            with ui.card().classes("w-full"):
                ui.label(t("import_csv.step2")).classes("text-lg font-semibold mb-2")
                ui.label(t("import_csv.upload_hint")).classes("text-sm text-grey-6 mb-3")

                status_label  = ui.label("").classes("text-sm")
                error_label   = ui.label("").classes("text-sm text-red-600")
                preview_table = ui.table(
                    columns=[
                        {"name": "date", "label": t("common.date"), "field": "date", "align": "left"},
                        {"name": "amount", "label": t("common.amount"), "field": "amount", "align": "right"},
                        {
                            "name": "description",
                            "label": t("common.description"),
                            "field": "description",
                            "align": "left",
                        },
                        {"name": "type", "label": t("common.type"), "field": "type", "align": "left"},
                    ],
                    rows=[],
                    row_key="idx",
                ).classes("w-full").props("dense")
                preview_table.visible = False
                import_btn = ui.button(
                    t("import_csv.import_all"), icon="upload", on_click=lambda: None
                ).props("color=primary")
                import_btn.visible = False

            # ── Step 3: detect transfers ────────────────────────────────────
            with ui.card().classes("w-full"):
                ui.label(t("import_csv.step3")).classes("text-lg font-semibold mb-1")
                ui.label(t("import_csv.transfer_hint")).classes("text-sm text-grey-6 mb-3")
                detect_result = ui.label("").classes("text-sm text-green-700")

                async def run_detect() -> None:
                    async with AsyncSessionFactory() as session:
                        svc = ImportService(session)
                        pairs = await svc.detect_and_link_transfers()
                    detect_result.set_text(t("import_csv.linked_pairs", count=pairs))
                    ui.notify(t("import_csv.linked_pairs", count=pairs), type="positive")

                ui.button(
                    t("import_csv.detect_transfers"), icon="compare_arrows", on_click=run_detect
                ).props("color=secondary")

            # ── Upload handler ───────────────────────────────────────────────
            async def handle_upload(e: events.UploadEventArguments) -> None:
                nonlocal parsed_result, preview_rows

                content = e.content.read().decode("utf-8", errors="replace")
                async with AsyncSessionFactory() as session:
                    result: ImportResult = ImportService(session).parse_csv(content)

                parsed_result = result.rows
                error_label.set_text("")
                preview_table.visible = False
                import_btn.visible    = False

                if result.errors:
                    error_label.set_text("\n".join(result.errors[:5]))
                if not result.rows:
                    status_label.set_text(t("import_csv.no_rows", skipped=result.skipped))
                    return

                preview_rows = [
                    {
                        "idx":         i,
                        "date":        str(r.date),
                        "amount":      f"{'+' if r.amount >= 0 else ''}{r.amount:,.2f}",
                        "description": r.description[:60],
                        "type":        "income" if r.amount >= 0 else "expense",
                    }
                    for i, r in enumerate(result.rows)
                ]
                preview_table.rows = preview_rows
                preview_table.visible = True
                import_btn.visible = True
                status_label.set_text(
                    t("import_csv.status", parsed=len(result.rows), imported=0, skipped=result.skipped)
                )

            async def do_import() -> None:
                if not account_sel.value:
                    ui.notify(t("import_csv.select_account_hint"), type="negative")
                    return
                async with AsyncSessionFactory() as session:
                    svc_import = ImportService(session)
                    creates = svc_import.to_transaction_creates(
                        parsed_result,
                        account_id=account_sel.value,
                        default_expense_category_id=expense_cat_sel.value,
                        default_income_category_id=income_cat_sel.value,
                    )
                    tx_svc = TransactionService(session)
                    for create in creates:
                        await tx_svc.create(create)

                ui.notify(t("import_csv.imported", count=len(creates)), type="positive")
                import_btn.visible = False
                status_label.set_text(t("import_csv.done", count=len(creates)))

            import_btn.on("click", do_import)

            ui.upload(
                label=t("import_csv.drop_hint"),
                on_upload=handle_upload,
                auto_upload=True,
            ).props("accept=.csv flat bordered").classes("w-full mt-2")
