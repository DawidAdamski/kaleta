# SPDX-License-Identifier: AGPL-3.0-or-later
"""mBank rows carry their final description from parse time to the stored row.

Plan ``import-preview-final-description``: the preview, the duplicate check
and the commit read one ``ParsedRow.description``, built by
``_build_mbank_description`` when the file is parsed. This drives the import
page's commit path (parse -> preview -> creates -> duplicates -> bulk create)
through the services against the database.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.account import AccountType
from kaleta.models.category import CategoryType
from kaleta.models.transaction import Transaction
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.category import CategoryCreate
from kaleta.services import AccountService, CategoryService, TransactionService
from kaleta.services.import_service import ImportService, build_preview_table_rows

STATEMENT = (
    "#Klient;\n"
    "Jan Kowalski;\n"
    "#Rodzaj rachunku;\n"
    "MKONTO INTENSIVE;\n"
    "#Waluta;\n"
    "PLN;\n"
    "#Numer rachunku;\n"
    "55 1140 2004 0000 3302 9999 6836 ;\n"
    "\n"
    "#Data księgowania;#Data operacji;#Opis operacji;#Tytuł;#Nadawca/Odbiorca;"
    "#Numer konta;#Kwota;#Saldo po operacji;\n"
    "2026-10-12;2026-10-10;ZAKUP PRZY UŻYCIU KARTY;"
    '"LIDL KASPROWICZA 01/INOWROCLAW  DATA TRANSAKCJI: 2026-10-10";"  ";\'\';'
    "-43,21;1 000,00;\n"
    "2026-10-14;2026-10-14;PRZELEW ZEWNĘTRZNY WYCHODZĄCY;"
    '"Czynsz 10/2026";"JAN NOWAK  UL. DŁUGA 1";\'12 1020 3040 0000 1111 2222 3333\';'
    "-2 400,00;956,79;\n"
)


async def _commit(session: AsyncSession, account_id: int, expense: int, income: int) -> int:
    """What the import page does for one queued mBank file; returns rows written."""
    svc = ImportService(session)
    parsed = svc.parse_queued_file(STATEMENT, "mbank")
    creates = await svc.to_transaction_creates_with_payees(
        parsed.rows,
        account_id=account_id,
        default_expense_category_id=expense,
        default_income_category_id=income,
    )
    creates, _skipped = await svc.filter_duplicates(creates)
    count = await TransactionService(session).create_bulk(creates)
    await session.commit()
    return count


async def test_mbank_preview_and_stored_row_read_the_same_description(
    session: AsyncSession,
) -> None:
    """Covers: KAL-CSV-040

    The preview shows the merchant (``LIDL KASPROWICZA 01/INOWROCLAW``), not
    ``ZAKUP PRZY UŻYCIU KARTY``; a transfer is still stored as
    ``Nadawca/Odbiorca — Tytuł``; and a second import of the same file is
    recognised as duplicates, because the duplicate check reads the same text.
    """
    account = await AccountService(session).create(
        AccountCreate(name="mBank KAL-CSV-040", type=AccountType.CHECKING)
    )
    expense = await CategoryService(session).create(
        CategoryCreate(name="KAL-CSV-040 expense", type=CategoryType.EXPENSE)
    )
    income = await CategoryService(session).create(
        CategoryCreate(name="KAL-CSV-040 income", type=CategoryType.INCOME)
    )

    parsed = ImportService(session).parse_queued_file(STATEMENT, "mbank")
    preview = build_preview_table_rows(parsed.rows, set(), profile="mbank")
    assert [p["description"] for p in preview] == [
        "LIDL KASPROWICZA 01/INOWROCLAW",
        "JAN NOWAK UL. DŁUGA 1 — Czynsz 10/2026",
    ]

    assert await _commit(session, account.id, expense.id, income.id) == 2
    stored = (
        await session.scalars(
            select(Transaction.description)
            .where(Transaction.account_id == account.id)
            .order_by(Transaction.date)
        )
    ).all()
    assert list(stored) == [
        "LIDL KASPROWICZA 01/INOWROCLAW",
        "JAN NOWAK UL. DŁUGA 1 — Czynsz 10/2026",
    ]

    assert await _commit(session, account.id, expense.id, income.id) == 0
