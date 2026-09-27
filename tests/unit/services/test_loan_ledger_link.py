# SPDX-License-Identifier: AGPL-3.0-or-later
"""Personal loans linked to ledger transactions (KAL-DBT-001, KAL-DBT-004).

A loan can point at the transaction that moved its principal, a repayment at
an existing transaction; every such transaction is loan money — kept out of
income and spending, reported under "Loans".
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import ConflictError, NotFoundError, ValidationError
from kaleta.models.account import AccountType
from kaleta.models.category import CategoryType
from kaleta.models.personal_loan import LoanDirection
from kaleta.models.transaction import TransactionType
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.category import CategoryCreate
from kaleta.schemas.personal_loan import (
    PersonalLoanCreate,
    PersonalLoanUpdate,
    RepaymentCreate,
)
from kaleta.schemas.transaction import TransactionCreate
from kaleta.services import (
    AccountService,
    CategoryService,
    PersonalLoanService,
    ReportService,
    TransactionService,
)
from kaleta.services.money_flow_service import (
    IN_LOANS_ID,
    OUT_LOANS_ID,
    POOL_ID,
    SURPLUS_ID,
    MoneyFlowService,
    month_bounds,
)
from kaleta.services.personal_loan_service import PersonalLoanFormError, parse_repayment_form

YESTERDAY = datetime.date(2026, 9, 26)


async def _account(session: AsyncSession, name: str = "Konto") -> int:
    acc = await AccountService(session).create(
        AccountCreate(name=name, type=AccountType.CHECKING, balance=Decimal("0.00"))
    )
    return acc.id


async def _category(session: AsyncSession, name: str, cat_type: CategoryType) -> int:
    cat = await CategoryService(session).create(CategoryCreate(name=name, type=cat_type))
    return cat.id


async def _default_category(session: AsyncSession, tx_type: TransactionType) -> int:
    """Income and expense need a category; give each type one shared 'Inne'."""
    cat_type = CategoryType.INCOME if tx_type == TransactionType.INCOME else CategoryType.EXPENSE
    for cat in await CategoryService(session).list():
        if cat.name == "Inne" and cat.type == cat_type:
            return cat.id
    return await _category(session, "Inne", cat_type)


async def _tx(
    session: AsyncSession,
    *,
    account_id: int,
    amount: str,
    tx_type: TransactionType = TransactionType.EXPENSE,
    date: datetime.date = YESTERDAY,
    category_id: int | None = None,
    description: str = "",
    is_internal_transfer: bool = False,
) -> int:
    if category_id is None and tx_type != TransactionType.TRANSFER:
        category_id = await _default_category(session, tx_type)
    tx = await TransactionService(session).create(
        TransactionCreate(
            account_id=account_id,
            category_id=category_id,
            amount=Decimal(amount),
            type=tx_type,
            date=date,
            description=description,
            is_internal_transfer=is_internal_transfer,
        )
    )
    return tx.id


async def _lend(
    session: AsyncSession,
    name: str,
    principal: str,
    *,
    transaction_id: int | None,
    direction: LoanDirection = LoanDirection.OUTGOING,
) -> int:
    svc = PersonalLoanService(session)
    cp = await svc.upsert_counterparty(name)
    loan = await svc.create_loan(
        PersonalLoanCreate(
            counterparty_id=cp.id,
            direction=direction,
            principal=Decimal(principal),
            opened_at=YESTERDAY,
            transaction_id=transaction_id,
        )
    )
    return loan.id


# ── KAL-DBT-001: link the loan to yesterday's transfer ───────────────────────


class TestLoanTransactionLink:
    async def test_lending_linked_to_yesterdays_transfer(self, session: AsyncSession) -> None:
        """Covers: KAL-DBT-001"""
        acc = await _account(session)
        transfer = await _tx(session, account_id=acc, amount="400.00", description="Dla Marka")

        loan_id = await _lend(session, "Marek", "400.00", transaction_id=transfer)

        svc = PersonalLoanService(session)
        loan = await svc.get_loan(loan_id)
        assert loan is not None
        assert loan.transaction_id == transfer
        totals = await svc.totals()
        assert totals.they_owe_you == Decimal("400.00")

    async def test_unknown_transaction_is_rejected(self, session: AsyncSession) -> None:
        with pytest.raises(NotFoundError):
            await _lend(session, "Marek", "400.00", transaction_id=9999)

    async def test_transaction_links_at_most_one_loan(self, session: AsyncSession) -> None:
        acc = await _account(session)
        transfer = await _tx(session, account_id=acc, amount="400.00")
        await _lend(session, "Marek", "400.00", transaction_id=transfer)

        with pytest.raises(ConflictError):
            await _lend(session, "Ania", "400.00", transaction_id=transfer)

    async def test_concurrent_link_is_a_conflict_not_a_crash(
        self, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        acc = await _account(session)
        transfer = await _tx(session, account_id=acc, amount="400.00")
        await _lend(session, "Marek", "400.00", transaction_id=transfer)

        # A request that passed the check before the first one committed.
        async def _passes(_self: PersonalLoanService, _tx_id: int) -> None:
            return None

        monkeypatch.setattr(PersonalLoanService, "_check_linkable", _passes)
        with pytest.raises(ConflictError):
            await _lend(session, "Ania", "400.00", transaction_id=transfer)

    async def test_update_can_set_and_keep_the_link(self, session: AsyncSession) -> None:
        acc = await _account(session)
        transfer = await _tx(session, account_id=acc, amount="400.00")
        loan_id = await _lend(session, "Marek", "400.00", transaction_id=None)
        svc = PersonalLoanService(session)

        await svc.update_loan(loan_id, PersonalLoanUpdate(transaction_id=transfer))
        # Re-saving the same link is not a conflict with itself.
        updated = await svc.update_loan(
            loan_id, PersonalLoanUpdate(transaction_id=transfer, notes="na wakacje")
        )

        assert updated is not None
        assert updated.transaction_id == transfer
        assert updated.notes == "na wakacje"

    async def test_repayment_links_an_existing_transaction(self, session: AsyncSession) -> None:
        acc = await _account(session)
        loan_id = await _lend(session, "Marek", "400.00", transaction_id=None)
        incoming = await _tx(
            session, account_id=acc, amount="250.00", tx_type=TransactionType.INCOME
        )
        svc = PersonalLoanService(session)

        rep = await svc.record_repayment(
            loan_id,
            RepaymentCreate(amount=Decimal("250.00"), date=YESTERDAY, link_transaction_id=incoming),
        )

        assert rep is not None
        assert rep.linked_transaction_id == incoming
        # Linking must not create a mirror transaction.
        txs = await TransactionService(session).list()
        assert [t.id for t in txs] == [incoming]
        assert (await svc.totals()).they_owe_you == Decimal("150.00")

    async def test_repayment_cannot_link_and_mirror(self, session: AsyncSession) -> None:
        acc = await _account(session)
        loan_id = await _lend(session, "Marek", "400.00", transaction_id=None)
        incoming = await _tx(
            session, account_id=acc, amount="250.00", tx_type=TransactionType.INCOME
        )

        with pytest.raises(ValidationError):
            await PersonalLoanService(session).record_repayment(
                loan_id,
                RepaymentCreate(
                    amount=Decimal("250.00"),
                    date=YESTERDAY,
                    link_transaction_id=incoming,
                    link_account_id=acc,
                ),
            )

    async def test_repayment_cannot_reuse_a_principal_transaction(
        self, session: AsyncSession
    ) -> None:
        acc = await _account(session)
        transfer = await _tx(session, account_id=acc, amount="400.00")
        loan_id = await _lend(session, "Marek", "400.00", transaction_id=transfer)

        with pytest.raises(ConflictError):
            await PersonalLoanService(session).record_repayment(
                loan_id,
                RepaymentCreate(
                    amount=Decimal("400.00"), date=YESTERDAY, link_transaction_id=transfer
                ),
            )

    async def test_link_candidates_skip_linked_and_internal(self, session: AsyncSession) -> None:
        acc = await _account(session)
        linked = await _tx(session, account_id=acc, amount="400.00")
        free = await _tx(session, account_id=acc, amount="50.00", description="Kino")
        await _tx(
            session,
            account_id=acc,
            amount="900.00",
            tx_type=TransactionType.TRANSFER,
            is_internal_transfer=True,
        )
        await _lend(session, "Marek", "400.00", transaction_id=linked)
        svc = PersonalLoanService(session)

        plain = await svc.list_link_candidates()
        with_own = await svc.list_link_candidates(include_ids=[linked])

        assert [c.id for c in plain] == [free]
        assert plain[0].description == "Kino"
        assert plain[0].account_name == "Konto"
        assert {c.id for c in with_own} == {free, linked}

    async def test_current_link_is_offered_beyond_the_limit(self, session: AsyncSession) -> None:
        acc = await _account(session)
        old = await _tx(session, account_id=acc, amount="400.00", date=datetime.date(2025, 1, 2))
        await _lend(session, "Marek", "400.00", transaction_id=old)
        newer = await _tx(session, account_id=acc, amount="20.00")

        found = await PersonalLoanService(session).list_link_candidates(limit=1, include_ids=[old])

        assert [c.id for c in found] == [newer, old]


class TestRepaymentFormLink:
    def test_existing_transaction_is_parsed(self) -> None:
        payload = parse_repayment_form(
            amount_value=250,
            date_value="2026-09-26",
            link_account_value=0,
            link_category_value=None,
            note_value="",
            link_transaction_value=7,
        )
        assert payload.link_transaction_id == 7
        assert payload.link_account_id is None

    def test_existing_transaction_and_mirror_account_conflict(self) -> None:
        with pytest.raises(PersonalLoanFormError):
            parse_repayment_form(
                amount_value=250,
                date_value="2026-09-26",
                link_account_value=3,
                link_category_value=None,
                note_value="",
                link_transaction_value=7,
            )


# ── KAL-DBT-004: lent money is not an expense ────────────────────────────────


class TestLoansAreNotSpending:
    async def _setup(self, session: AsyncSession) -> tuple[int, int]:
        acc = await _account(session)
        food = await _category(session, "Jedzenie", CategoryType.EXPENSE)
        salary = await _category(session, "Pensja", CategoryType.INCOME)
        await _tx(
            session,
            account_id=acc,
            amount="3000.00",
            tx_type=TransactionType.INCOME,
            category_id=salary,
        )
        await _tx(session, account_id=acc, amount="120.00", category_id=food)
        transfer = await _tx(session, account_id=acc, amount="400.00", category_id=food)
        await _lend(session, "Marek", "400.00", transaction_id=transfer)
        return acc, food

    async def test_monthly_summary_shows_loan_under_loans(self, session: AsyncSession) -> None:
        """Covers: KAL-DBT-004"""
        await self._setup(session)

        stmt = await ReportService(session).income_statement(2026, 9)

        assert stmt.total_expenses == Decimal("120.00")
        assert [(c.category, c.amount) for c in stmt.expense_by_category] == [
            ("Jedzenie", Decimal("120.00"))
        ]
        assert stmt.loans_out == Decimal("400.00")
        assert stmt.loans_in == Decimal("0.00")
        assert stmt.total_income == Decimal("3000.00")

    async def test_month_kpis_exclude_loan_money(self, session: AsyncSession) -> None:
        await self._setup(session)

        income, expenses = await ReportService(session)._month_summary(2026, 9)

        assert income == Decimal("3000.00")
        assert expenses == Decimal("120.00")

    async def test_linked_repayment_is_not_income(self, session: AsyncSession) -> None:
        acc, _ = await self._setup(session)
        loan_id = (await PersonalLoanService(session).list_loans())[0].id
        back = await _tx(session, account_id=acc, amount="250.00", tx_type=TransactionType.INCOME)
        await PersonalLoanService(session).record_repayment(
            loan_id,
            RepaymentCreate(amount=Decimal("250.00"), date=YESTERDAY, link_transaction_id=back),
        )

        stmt = await ReportService(session).income_statement(2026, 9)

        assert stmt.total_income == Decimal("3000.00")
        assert stmt.loans_in == Decimal("250.00")

    async def test_money_flow_draws_loans_as_their_own_node(self, session: AsyncSession) -> None:
        """Covers: KAL-DBT-004"""
        await self._setup(session)
        start, end = month_bounds(2026, 9)

        flow = await MoneyFlowService(session).build(start, end)

        assert flow.total_out == Decimal("120.00")
        assert flow.loans_out == Decimal("400.00")
        links = {(lk.source, lk.target): lk.amount for lk in flow.links}
        assert links[(POOL_ID, OUT_LOANS_ID)] == Decimal("400.00")
        # The pool still balances cash: 3000 in − 120 spent − 400 lent.
        assert links[(POOL_ID, SURPLUS_ID)] == Decimal("2480.00")
        assert IN_LOANS_ID not in {n.id for n in flow.nodes}
        assert "Loans" in {n.label for n in flow.nodes}

    async def test_money_flow_accounts_lens_routes_loans(self, session: AsyncSession) -> None:
        acc, _ = await self._setup(session)
        start, end = month_bounds(2026, 9)

        flow = await MoneyFlowService(session).build(start, end, mode="accounts")

        links = {(lk.source, lk.target): lk.amount for lk in flow.links}
        assert links[(f"acc:{acc}", OUT_LOANS_ID)] == Decimal("400.00")
        assert flow.total_out == Decimal("120.00")
