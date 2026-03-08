from __future__ import annotations

from nicegui import events, ui

from kaleta.db import AsyncSessionFactory
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

        with page_layout("Import CSV"):
            ui.label("Import Transactions from CSV").classes("text-2xl font-bold")

            # ── Step 1: settings ────────────────────────────────────────────
            with ui.card().classes("w-full"):
                ui.label("Step 1 — Settings").classes("text-lg font-semibold mb-2")
                with ui.row().classes("w-full gap-4 flex-wrap"):
                    account_sel = ui.select(account_options, label="Target Account").classes("flex-1 min-w-48")
                    if account_options:
                        account_sel.value = next(iter(account_options))
                    expense_cat_sel = ui.select(expense_cat_opts, label="Default Expense Category").classes("flex-1 min-w-48")
                    income_cat_sel  = ui.select(income_cat_opts,  label="Default Income Category").classes("flex-1 min-w-48")

            # ── Step 2: upload ───────────────────────────────────────────────
            with ui.card().classes("w-full"):
                ui.label("Step 2 — Upload CSV File").classes("text-lg font-semibold mb-2")
                ui.label(
                    "Supported columns: date / amount (or debit + credit) / description. "
                    "Auto-detects delimiter (comma, semicolon, tab) and date format."
                ).classes("text-sm text-grey-6 mb-3")

                status_label  = ui.label("").classes("text-sm")
                error_label   = ui.label("").classes("text-sm text-red-600")
                preview_table = ui.table(
                    columns=[
                        {"name": "date",        "label": "Date",        "field": "date",        "align": "left"},
                        {"name": "amount",      "label": "Amount",      "field": "amount",      "align": "right"},
                        {"name": "description", "label": "Description", "field": "description", "align": "left"},
                        {"name": "type",        "label": "Type",        "field": "type",        "align": "left"},
                    ],
                    rows=[],
                    row_key="idx",
                ).classes("w-full").props("dense")
                preview_table.visible = False
                import_btn = ui.button("Import All", icon="upload", on_click=lambda: None).props(
                    "color=primary"
                )
                import_btn.visible = False

            # ── Step 3: detect transfers ────────────────────────────────────
            with ui.card().classes("w-full"):
                ui.label("Step 3 — Detect Internal Transfers").classes("text-lg font-semibold mb-1")
                ui.label(
                    "After importing, scan all unlinked transfer transactions and pair "
                    "matching outflow / inflow legs automatically."
                ).classes("text-sm text-grey-6 mb-3")
                detect_result = ui.label("").classes("text-sm text-green-700")

                async def run_detect() -> None:
                    async with AsyncSessionFactory() as session:
                        svc = ImportService(session)
                        pairs = await svc.detect_and_link_transfers()
                    detect_result.set_text(f"Linked {pairs} transfer pair(s).")
                    ui.notify(f"Linked {pairs} transfer pair(s).", type="positive")

                ui.button("Detect & Link Transfers", icon="compare_arrows", on_click=run_detect).props(
                    "color=secondary"
                )

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
                    status_label.set_text(f"No rows parsed. Skipped: {result.skipped}.")
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
                    f"Parsed {len(result.rows)} rows, skipped {result.skipped}. "
                    f"Review and click Import."
                )

            async def do_import() -> None:
                if not account_sel.value:
                    ui.notify("Select a target account.", type="negative")
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

                ui.notify(f"Imported {len(creates)} transactions.", type="positive")
                import_btn.visible = False
                status_label.set_text(f"Done. Imported {len(creates)} transactions.")

            import_btn.on("click", do_import)

            ui.upload(
                label="Drop CSV here or click to browse",
                on_upload=handle_upload,
                auto_upload=True,
            ).props("accept=.csv flat bordered").classes("w-full mt-2")
