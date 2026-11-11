# SPDX-License-Identifier: AGPL-3.0-or-later
"""``ImportPipeline``: ``build`` writes nothing, ``apply`` writes everything once."""

from __future__ import annotations

import dataclasses
import datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import ValidationError
from kaleta.models.account import AccountType
from kaleta.models.category import CategoryType
from kaleta.models.import_run import ImportRun
from kaleta.models.payee import Payee
from kaleta.models.transaction import Transaction, TransactionType
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.categorisation_rule import CategorisationRuleCreate
from kaleta.schemas.category import CategoryCreate
from kaleta.schemas.import_rule import ImportRuleCreate
from kaleta.services import AccountService, CategoryService
from kaleta.services.import_pipeline import (
    SKIP_DUPLICATE,
    ImportOptions,
    ImportPipeline,
    upload_exceeds_limit,
)
from kaleta.services.import_profiles import MBANK_PROFILE
from kaleta.services.import_rule_service import ImportRuleService
from kaleta.services.import_service import MBankFileMetadata, ParsedRow, ParseQueuedFileResult
from kaleta.services.rule_service import RuleService

STATEMENT_NUMBER = "55114020040000330299996836"
DAY = datetime.date(2026, 7, 1)


def _meta(currency: str = "PLN", number: str = STATEMENT_NUMBER) -> MBankFileMetadata:
    return MBankFileMetadata(
        client_name="Jan Kowalski",
        account_type="MKONTO INTENSIVE",
        currency=currency,
        account_number=number,
        account_number_digits=number,
        date_from=None,
        date_to=None,
    )


def _row(amount: str, description: str, payee: str = "", day: datetime.date = DAY) -> ParsedRow:
    return ParsedRow(
        date=day,
        amount=Decimal(amount),
        description=description,
        raw={"Nadawca/Odbiorca": payee, "Numer konta": ""},
    )


def _mbank(*rows: ParsedRow, meta: MBankFileMetadata | None = None) -> ParseQueuedFileResult:
    return ParseQueuedFileResult(
        profile=MBANK_PROFILE, rows=list(rows), metadata=meta or _meta(), ok=True
    )


class _Setup:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def make(self) -> _Setup:
        accounts = AccountService(self.session)
        self.mkonto = (
            await accounts.create(AccountCreate(name="mKonto", type=AccountType.CHECKING))
        ).id
        self.savings = (
            await accounts.create(AccountCreate(name="Savings", type=AccountType.SAVINGS))
        ).id
        self.eur = (
            await accounts.create(
                AccountCreate(name="Wise EUR", type=AccountType.CHECKING, currency="EUR")
            )
        ).id
        categories = CategoryService(self.session)
        self.spend = (
            await categories.create(CategoryCreate(name="Other", type=CategoryType.EXPENSE))
        ).id
        self.earn = (
            await categories.create(CategoryCreate(name="Inflow", type=CategoryType.INCOME))
        ).id
        return self

    def options(self, **changes: Any) -> ImportOptions:
        base = ImportOptions(
            filename="mkonto_2026-07.csv",
            account_id=self.mkonto,
            expense_category_id=self.spend,
            income_category_id=self.earn,
        )
        return dataclasses.replace(base, **changes)

    async def counts(self) -> tuple[int, int, int]:
        async def count(model: type) -> int:
            return int(await self.session.scalar(select(func.count()).select_from(model)) or 0)

        return await count(Transaction), await count(Payee), await count(ImportRun)


@pytest.fixture
async def env(session: AsyncSession) -> _Setup:
    return await _Setup(session).make()


class TestBuild:
    async def test_build_writes_nothing(self, env: _Setup, session: AsyncSession) -> None:
        before = await env.counts()
        plan = await ImportPipeline(session).build(
            _mbank(
                _row("-209.98", "KAUFLAND", payee="Kaufland Inowrocław"),
                _row("-13.90", "McDonalds", payee="McDonalds 219"),
                _row("620.00", "WPŁATA"),
            ),
            env.options(),
        )
        await session.commit()  # anything staged would land now
        assert await env.counts() == before
        assert len(plan.rows) == 3
        assert plan.new_payee_names == ["Kaufland Inowrocław", "McDonalds 219"]
        assert plan.account_number_digits == STATEMENT_NUMBER

    async def test_existing_payee_is_matched_not_named(
        self, env: _Setup, session: AsyncSession
    ) -> None:
        pipeline = ImportPipeline(session)
        first = await pipeline.build(_mbank(_row("-5.00", "x", payee="Żabka")), env.options())
        await pipeline.apply(first)
        plan = await pipeline.build(
            _mbank(_row("-6.00", "y", payee="Żabka", day=DAY + datetime.timedelta(days=1))),
            env.options(),
        )
        assert plan.new_payee_names == []
        assert plan.rows[0].create.payee_id is not None

    async def test_duplicates_are_skipped_with_a_reason(
        self, env: _Setup, session: AsyncSession
    ) -> None:
        pipeline = ImportPipeline(session)
        await pipeline.apply(
            await pipeline.build(_mbank(_row("-5.00", "BIEDRONKA")), env.options())
        )
        plan = await pipeline.build(
            _mbank(_row("-5.00", "BIEDRONKA"), _row("-7.00", "LIDL")), env.options()
        )
        assert [r.create.description for r in plan.rows] == ["LIDL"]
        assert [(s.create.description, s.reason) for s in plan.skipped] == [
            ("BIEDRONKA", SKIP_DUPLICATE)
        ]
        kept = await pipeline.build(
            _mbank(_row("-5.00", "BIEDRONKA")), env.options(skip_duplicates=False)
        )
        assert len(kept.rows) == 1

    async def test_rules_see_the_name_of_a_payee_not_created_yet(
        self, env: _Setup, session: AsyncSession
    ) -> None:
        groceries = (
            await CategoryService(session).create(
                CategoryCreate(name="Groceries", type=CategoryType.EXPENSE)
            )
        ).id
        await RuleService(session).create(
            CategorisationRuleCreate(pattern="Kaufland", category_id=groceries)
        )
        plan = await ImportPipeline(session).build(
            _mbank(_row("-209.98", "ZAKUP PRZY UŻYCIU KARTY", payee="Kaufland Inowrocław")),
            env.options(),
        )
        assert plan.rows[0].create.payee_id is None
        assert plan.rows[0].create.category_id == groceries

    async def test_known_numbers_are_read_on_every_build(
        self, env: _Setup, session: AsyncSession
    ) -> None:
        savings_number = "96132015374150799939999901"
        transfer = ParsedRow(
            date=DAY,
            amount=Decimal("-500.00"),
            description="PRZELEW WŁASNY",
            raw={"Nadawca/Odbiorca": "", "Numer konta": f"'{savings_number}'"},
        )
        pipeline = ImportPipeline(session)
        before = await pipeline.build(_mbank(transfer), env.options())
        assert before.rows[0].create.type == TransactionType.EXPENSE
        await AccountService(session).save_external_number(env.savings, savings_number)
        after = await pipeline.build(_mbank(transfer), env.options())
        assert after.rows[0].create.type == TransactionType.TRANSFER

    async def test_transfer_window_spans_every_parsed_row(
        self, env: _Setup, session: AsyncSession
    ) -> None:
        plan = await ImportPipeline(session).build(
            _mbank(_row("-1.00", "a"), _row("-2.00", "b", day=DAY + datetime.timedelta(days=5))),
            env.options(pairing_days=3),
        )
        assert plan.transfer_window == (
            DAY - datetime.timedelta(days=3),
            DAY + datetime.timedelta(days=8),
        )


class TestReadiness:
    @pytest.mark.parametrize(
        ("override", "key"),
        [
            ({"expense_category_id": None}, "import.select_expense_cat_hint"),
            ({"income_category_id": None}, "import.select_income_cat_hint"),
        ],
    )
    async def test_missing_default_category(
        self, env: _Setup, session: AsyncSession, override: dict, key: str
    ) -> None:
        with pytest.raises(ValidationError) as caught:
            await ImportPipeline(session).build(_mbank(_row("-1.00", "a")), env.options(**override))
        assert caught.value.message_key == key

    async def test_no_account_found(self, env: _Setup, session: AsyncSession) -> None:
        with pytest.raises(ValidationError) as caught:
            await ImportPipeline(session).build(
                _mbank(_row("-1.00", "a")), env.options(account_id=None, filename="unknown.csv")
            )
        assert caught.value.message_key == "import.select_account_hint"

    async def test_currency_mismatch(self, env: _Setup, session: AsyncSession) -> None:
        with pytest.raises(ValidationError) as caught:
            await ImportPipeline(session).build(
                _mbank(_row("-1.00", "a")), env.options(account_id=env.eur)
            )
        assert caught.value.message_key == "import.currency_mismatch_block"
        assert caught.value.params == {"file": "PLN", "account": "EUR"}


class TestAccountResolution:
    async def test_account_resolution_order(self, env: _Setup, session: AsyncSession) -> None:
        await AccountService(session).save_external_number(env.savings, STATEMENT_NUMBER)
        pipeline = ImportPipeline(session)

        async def resolve(filename: str, account_id: int | None = None) -> tuple:
            r = await pipeline.resolve_account(
                filename=filename, profile=MBANK_PROFILE, metadata=_meta(), account_id=account_id
            )
            return r.account_id, r.source

        # number alone
        assert await resolve("statement.csv") == (env.savings, "number")
        # a filename rule beats the number
        await ImportRuleService(session).create(
            ImportRuleCreate(filename_pattern="mkonto_*", account_id=env.mkonto)
        )
        assert await resolve("mkonto_2026-07.csv") == (env.mkonto, "rule")
        # an explicit account beats the rule
        assert await resolve("mkonto_2026-07.csv", account_id=env.eur) == (env.eur, "explicit")

    async def test_number_account_is_reported_when_a_rule_wins(
        self, env: _Setup, session: AsyncSession
    ) -> None:
        await AccountService(session).save_external_number(env.savings, STATEMENT_NUMBER)
        await ImportRuleService(session).create(
            ImportRuleCreate(filename_pattern="mkonto_*", account_id=env.mkonto)
        )
        r = await ImportPipeline(session).resolve_account(
            filename="mkonto_2026-07.csv", profile=MBANK_PROFILE, metadata=_meta()
        )
        assert (r.source, r.number_account_id) == ("rule", env.savings)

    async def test_build_without_account_uses_the_resolution(
        self, env: _Setup, session: AsyncSession
    ) -> None:
        await AccountService(session).save_external_number(env.savings, STATEMENT_NUMBER)
        plan = await ImportPipeline(session).build(
            _mbank(_row("-1.00", "a")), env.options(account_id=None, filename="statement.csv")
        )
        assert plan.account_id == env.savings
        assert plan.resolution.source == "number"


class TestApply:
    async def test_apply_writes_rows_payees_run_and_number(
        self, env: _Setup, session: AsyncSession
    ) -> None:
        pipeline = ImportPipeline(session)
        plan = await pipeline.build(
            _mbank(
                _row("-209.98", "KAUFLAND", payee="Kaufland Inowrocław"),
                _row("-82.04", "KAUFLAND 2", payee="Kaufland Inowrocław"),
                _row("620.00", "WPŁATA"),
            ),
            env.options(),
        )
        outcome = await pipeline.apply(plan)
        assert outcome.imported_count == 3
        assert outcome.created_payee_count == 1
        assert await env.counts() == (3, 1, 1)
        run = await session.get(ImportRun, outcome.import_run_id)
        assert run is not None
        assert (run.imported_count, run.skipped_count) == (3, 0)
        account = await AccountService(session).get(env.mkonto)
        assert account is not None
        assert account.external_account_number == STATEMENT_NUMBER

    async def test_apply_is_atomic(
        self, env: _Setup, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pipeline = ImportPipeline(session)
        plan = await pipeline.build(
            _mbank(_row("-209.98", "KAUFLAND", payee="Kaufland Inowrocław")), env.options()
        )
        before = await env.counts()

        async def boom(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("disk full")

        monkeypatch.setattr(AccountService, "save_external_number", boom)
        with pytest.raises(RuntimeError, match="disk full"):
            await pipeline.apply(plan)
        assert await env.counts() == before
        account = await AccountService(session).get(env.mkonto)
        assert account is not None
        assert account.external_account_number is None


def test_upload_limit_is_the_settings_cap() -> None:
    assert upload_exceeds_limit(1025, cap_bytes=1024) is True
    assert upload_exceeds_limit(1024, cap_bytes=1024) is False
