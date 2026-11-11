# SPDX-License-Identifier: AGPL-3.0-or-later
"""The import pipeline end to end on a real mBank export shape.

Covers: KAL-CSV-043

``current-account-sample.csv`` (anonymised dogfood) parsed, built and applied
exactly as the import page does; the stored rows are compared with literals
read off the file itself (Working Agreement rule 11), not with "what the old
code produced".
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.account import AccountType
from kaleta.models.category import CategoryType
from kaleta.models.import_run import ImportRun
from kaleta.models.payee import Payee
from kaleta.models.transaction import Transaction
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.categorisation_rule import CategorisationRuleCreate
from kaleta.schemas.category import CategoryCreate
from kaleta.schemas.import_rule import ImportRuleCreate
from kaleta.services import AccountService, CategoryService
from kaleta.services.import_pipeline import ImportOptions, ImportPipeline
from kaleta.services.import_rule_service import ImportRuleService
from kaleta.services.import_service import (
    ImportService,
    MBankFileMetadata,
    ParsedRow,
    ParseQueuedFileResult,
)
from kaleta.services.rule_service import RuleService

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "e2e"
    / "fixtures"
    / "import"
    / "mbank"
    / "current-account-sample.csv"
)
#: The statement's own number (``#Numer rachunku``) and the savings account
#: the "PRZELEW WEWNĘTRZNY PRZYCHODZĄCY" row came from (its ``#Numer konta``).
STATEMENT_NUMBER = "55114020040000330299996836"
SAVINGS_NUMBER = "96132015374150799939999901"

# date, type, amount, category, description — one per data row of the file.
GOLDEN = [
    ("2019-06-12", "income", "0.00", "Inflow", "OTWARCIE RACHUNKU"),
    (
        "2019-06-24",
        "transfer",
        "1000.00",
        None,
        "Anna Nowak CHEŁMICZKI 38 88-121 CHEŁMCE — nasze 96132015374150799939999901",
    ),
    ("2019-06-26", "expense", "209.98", "Other", "KAUFLAND /INOWROCLAW"),
    ("2019-06-27", "expense", "82.04", "Other", "BP-SOLNICA 446 /INOWROCLAW"),
    ("2019-06-28", "expense", "13.90", "Other", "McDonalds 219 Inowr/Inowroclaw"),
    ("2019-06-28", "expense", "294.48", "Other", "KAUFLAND /INOWROCLAW"),
    ("2019-06-28", "expense", "143.10", "Other", "BP-SOLNICA 446 /INOWROCLAW"),
    ("2019-06-29", "expense", "6.00", "Other", "Pauza 1 /Bydgoszcz"),
    ("2019-06-29", "expense", "73.71", "Other", "BP-SOLNO 538 /INOWROCLAW"),
    ("2019-07-03", "expense", "10.97", "Other", "CARREFOUR HIPERMARK/INOWROCLAW"),
    ("2019-07-06", "expense", "44.57", "Groceries", "JMP S.A. BIEDRONKA /INOWROCLAW"),
    ("2019-07-09", "income", "620.00", "Inflow", "4275WPŁATOMATEURONET/000091272"),
]


async def test_pipeline_matches_golden_rows(session: AsyncSession) -> None:
    accounts = AccountService(session)
    mkonto = await accounts.create(AccountCreate(name="mKonto", type=AccountType.CHECKING))
    savings = await accounts.create(AccountCreate(name="Savings", type=AccountType.SAVINGS))
    await accounts.save_external_number(savings.id, SAVINGS_NUMBER)
    categories = CategoryService(session)
    names: dict[int | None, str | None] = {None: None}
    other = await categories.create(CategoryCreate(name="Other", type=CategoryType.EXPENSE))
    inflow = await categories.create(CategoryCreate(name="Inflow", type=CategoryType.INCOME))
    groceries = await categories.create(CategoryCreate(name="Groceries", type=CategoryType.EXPENSE))
    for category in (other, inflow, groceries):
        names[category.id] = category.name
    await RuleService(session).create(
        CategorisationRuleCreate(pattern="BIEDRONKA", category_id=groceries.id)
    )

    parsed = ImportService(session).parse_queued_file(
        FIXTURE.read_text(encoding="utf-8"), "generic", filename=FIXTURE.name
    )
    pipeline = ImportPipeline(session)
    plan = await pipeline.build(
        parsed,
        ImportOptions(
            filename=FIXTURE.name,
            account_id=mkonto.id,
            expense_category_id=other.id,
            income_category_id=inflow.id,
        ),
    )
    assert plan.new_payee_names == ["Anna Nowak CHEŁMICZKI 38 88-121 CHEŁMCE"]
    outcome = await pipeline.apply(plan)

    stored = (
        (await session.execute(select(Transaction).order_by(Transaction.date, Transaction.id)))
        .scalars()
        .all()
    )
    assert [
        (str(t.date), t.type.value, str(t.amount), names[t.category_id], t.description)
        for t in stored
    ] == GOLDEN
    assert all(t.account_id == mkonto.id for t in stored)
    transfer = stored[1]
    assert transfer.is_internal_transfer is True
    assert transfer.amount == Decimal("1000.00")
    assert transfer.payee_id is not None

    assert outcome.imported_count == 12
    run = await session.get(ImportRun, outcome.import_run_id)
    assert run is not None
    assert (run.filename, run.profile, run.imported_count, run.skipped_count) == (
        "current-account-sample.csv",
        "mbank",
        12,
        0,
    )
    refreshed = await accounts.get(mkonto.id)
    assert refreshed is not None
    assert refreshed.external_account_number == STATEMENT_NUMBER

    # The same file again: every row is a duplicate, nothing is written.
    again = await pipeline.apply(
        await pipeline.build(
            parsed,
            ImportOptions(
                filename=FIXTURE.name,
                account_id=mkonto.id,
                expense_category_id=other.id,
                income_category_id=inflow.id,
            ),
        )
    )
    assert (again.imported_count, len(again.skipped)) == (0, 12)


STATEMENT_META_NUMBER = "55114020040000330299996836"  # "55 1140 2004 0000 3302 9999 6836"


def _statement(*rows: ParsedRow) -> ParseQueuedFileResult:
    meta = MBankFileMetadata(
        client_name="Jan Kowalski",
        account_type="MKONTO INTENSIVE",
        currency="PLN",
        account_number="55 1140 2004 0000 3302 9999 6836",
        account_number_digits=STATEMENT_META_NUMBER,
        date_from=None,
        date_to=None,
    )
    return ParseQueuedFileResult(profile="mbank", rows=list(rows), metadata=meta, ok=True)


async def _accounts_and_categories(session: AsyncSession) -> tuple[int, int, int, int]:
    accounts = AccountService(session)
    mkonto = await accounts.create(AccountCreate(name="mKonto", type=AccountType.CHECKING))
    savings = await accounts.create(AccountCreate(name="Savings", type=AccountType.SAVINGS))
    categories = CategoryService(session)
    other = await categories.create(CategoryCreate(name="Other", type=CategoryType.EXPENSE))
    inflow = await categories.create(CategoryCreate(name="Inflow", type=CategoryType.INCOME))
    return mkonto.id, savings.id, other.id, inflow.id


async def test_filename_rule_beats_statement_number(session: AsyncSession) -> None:
    """Covers: KAL-CSV-043"""
    mkonto, savings, other, inflow = await _accounts_and_categories(session)
    await AccountService(session).save_external_number(savings, "55 1140 2004 0000 3302 9999 6836")
    await ImportRuleService(session).create(
        ImportRuleCreate(filename_pattern="mkonto_*", account_id=mkonto)
    )
    pipeline = ImportPipeline(session)
    row = ParsedRow(
        date=datetime.date(2026, 7, 1),
        amount=Decimal("-10.00"),
        description="ZAKUP",
        raw={"Nadawca/Odbiorca": "", "Numer konta": ""},
    )

    by_rule = await pipeline.build(
        _statement(row),
        ImportOptions(
            filename="mkonto_2026-07.csv", expense_category_id=other, income_category_id=inflow
        ),
    )
    assert (by_rule.account_id, by_rule.resolution.source) == (mkonto, "rule")
    assert by_rule.resolution.number_account_id == savings

    by_number = await pipeline.build(
        _statement(row),
        ImportOptions(
            filename="statement.csv", expense_category_id=other, income_category_id=inflow
        ),
    )
    assert (by_number.account_id, by_number.resolution.source) == (savings, "number")


async def test_skipped_duplicates_create_no_payees(session: AsyncSession) -> None:
    """Covers: KAL-CSV-043

    The old flow created every row's payee before dropping duplicates, which
    left a payee behind for a row that was never stored.
    """
    mkonto, _savings, other, inflow = await _accounts_and_categories(session)
    pipeline = ImportPipeline(session)
    options = ImportOptions(
        filename="mkonto_2026-07.csv",
        account_id=mkonto,
        expense_category_id=other,
        income_category_id=inflow,
    )

    def zakup(payee: str) -> ParsedRow:
        return ParsedRow(
            date=datetime.date(2026, 7, 1),
            amount=Decimal("-10.00"),
            description="ZAKUP",
            raw={"Nadawca/Odbiorca": payee, "Numer konta": ""},
        )

    await pipeline.apply(await pipeline.build(_statement(zakup("")), options))
    payees_before = await session.scalar(select(func.count()).select_from(Payee))

    plan = await pipeline.build(_statement(zakup("Sklep Nowy")), options)
    assert len(plan.skipped) == 1
    assert plan.new_payee_names == []
    outcome = await pipeline.apply(plan)
    assert (outcome.imported_count, outcome.created_payee_count) == (0, 0)
    assert await session.scalar(select(func.count()).select_from(Payee)) == payees_before
