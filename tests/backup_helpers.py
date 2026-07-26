# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared helpers for BackupService round-trip tests."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models import (
    Account,
    AccountType,
    ApiToken,
    Asset,
    AssetType,
    AuditLog,
    Budget,
    CategorisationRule,
    Category,
    CategoryType,
    Counterparty,
    CreditCardProfile,
    CurrencyRate,
    DismissedCandidate,
    Institution,
    InstitutionType,
    LoanDirection,
    LoanProfile,
    LoanStatus,
    MonthlyReadiness,
    Payee,
    PersonalLoan,
    PersonalLoanRepayment,
    PlannedTransaction,
    RecurrenceFrequency,
    ReserveFund,
    ReserveFundBackingMode,
    ReserveFundKind,
    RuleMatchMode,
    SavedReport,
    Subscription,
    SubscriptionStatus,
    Tag,
    Transaction,
    TransactionSplit,
    TransactionType,
    User,
    YearlyPlan,
    transaction_tags,
)
from kaleta.services.backup_service import _backup_tables, _set_sqlite_foreign_keys


async def row_counts(session: AsyncSession) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in _backup_tables():
        # nosec B608: table names from Base.metadata only.
        result = await session.execute(text(f"SELECT COUNT(*) FROM {table}"))  # nosec B608
        counts[table] = int(result.scalar_one())
    return counts


async def wipe_all(session: AsyncSession) -> None:
    await _set_sqlite_foreign_keys(session, enabled=False)
    for table in reversed(_backup_tables()):
        # nosec B608: table names from Base.metadata only.
        await session.execute(text(f"DELETE FROM {table}"))  # nosec B608
    await session.commit()
    await _set_sqlite_foreign_keys(session, enabled=True)


async def seed_every_model(session: AsyncSession) -> None:
    """Insert at least one row into every ORM table (incl. association tables)."""
    user = User(username="backup-user", password_hash="argon2-not-a-real-hash")
    session.add(user)
    await session.flush()

    institution = Institution(name="mBank", type=InstitutionType.BANK, color="#000000")
    session.add(institution)
    await session.flush()

    account = Account(
        name="Checking",
        type=AccountType.CHECKING,
        balance=Decimal("1000.00"),
        currency="PLN",
        institution_id=institution.id,
        user_id=user.id,
    )
    credit_account = Account(
        name="Credit card",
        type=AccountType.CREDIT,
        balance=Decimal("-200.00"),
        currency="PLN",
        institution_id=institution.id,
        user_id=user.id,
    )
    loan_account = Account(
        name="Car loan",
        type=AccountType.CREDIT,
        balance=Decimal("-5000.00"),
        currency="PLN",
        user_id=user.id,
    )
    session.add_all([account, credit_account, loan_account])
    await session.flush()

    category = Category(name="Food", type=CategoryType.EXPENSE, user_id=user.id)
    session.add(category)
    await session.flush()

    session.add(
        CategorisationRule(
            pattern="LIDL",
            match_mode=RuleMatchMode.CONTAINS,
            category_id=category.id,
            is_active=True,
            priority=0,
            user_id=user.id,
        )
    )

    payee = Payee(name="Biedronka", user_id=user.id)
    session.add(payee)
    await session.flush()

    tag = Tag(name="groceries", color="#112233", user_id=user.id)
    session.add(tag)
    await session.flush()

    txn = Transaction(
        account_id=account.id,
        category_id=category.id,
        payee_id=payee.id,
        amount=Decimal("42.50"),
        type=TransactionType.EXPENSE,
        date=date(2024, 6, 1),
        description="Weekly shop",
        is_split=True,
        user_id=user.id,
    )
    session.add(txn)
    await session.flush()

    session.add(
        TransactionSplit(
            transaction_id=txn.id,
            category_id=category.id,
            amount=Decimal("42.50"),
            note="all food",
        )
    )
    await session.execute(transaction_tags.insert().values(transaction_id=txn.id, tag_id=tag.id))

    session.add(
        Budget(
            category_id=category.id,
            amount=Decimal("800.00"),
            month=6,
            year=2024,
            user_id=user.id,
        )
    )
    session.add(
        Asset(
            name="Bike",
            type=AssetType.OTHER,
            value=Decimal("1500.00"),
            description="City bike",
            user_id=user.id,
        )
    )
    session.add(
        CurrencyRate(
            date=date(2024, 6, 1),
            from_currency="EUR",
            to_currency="PLN",
            rate=Decimal("4.300000"),
        )
    )
    session.add(
        CreditCardProfile(
            account_id=credit_account.id,
            credit_limit=Decimal("10000.00"),
            statement_day=5,
            payment_due_day=25,
            user_id=user.id,
        )
    )
    session.add(
        LoanProfile(
            account_id=loan_account.id,
            principal=Decimal("20000.00"),
            apr=Decimal("7.50"),
            term_months=48,
            start_date=date(2023, 1, 1),
            monthly_payment=Decimal("480.00"),
            user_id=user.id,
        )
    )
    session.add(
        PlannedTransaction(
            name="Rent",
            amount=Decimal("2500.00"),
            type=TransactionType.EXPENSE,
            account_id=account.id,
            category_id=category.id,
            frequency=RecurrenceFrequency.MONTHLY,
            start_date=date(2024, 1, 1),
            user_id=user.id,
        )
    )
    session.add(
        Subscription(
            payee_id=payee.id,
            category_id=category.id,
            name="Netflix",
            amount=Decimal("43.00"),
            cadence_days=30,
            first_seen_at=date(2024, 1, 15),
            next_expected_at=date(2024, 7, 15),
            status=SubscriptionStatus.ACTIVE,
            user_id=user.id,
        )
    )
    session.add(
        DismissedCandidate(
            payee_id=payee.id,
            merchant_key=None,
            amount_bucket="40-50",
        )
    )

    counterparty = Counterparty(name="Anna Kowalska", user_id=user.id)
    session.add(counterparty)
    await session.flush()
    loan = PersonalLoan(
        counterparty_id=counterparty.id,
        direction=LoanDirection.OUTGOING,
        principal=Decimal("500.00"),
        currency="PLN",
        opened_at=date(2024, 3, 1),
        status=LoanStatus.OUTSTANDING,
        user_id=user.id,
    )
    session.add(loan)
    await session.flush()
    session.add(
        PersonalLoanRepayment(
            loan_id=loan.id,
            amount=Decimal("100.00"),
            date=date(2024, 4, 1),
            note="partial",
            linked_transaction_id=None,
        )
    )

    session.add(
        ReserveFund(
            name="Emergency",
            kind=ReserveFundKind.EMERGENCY,
            target_amount=Decimal("10000.00"),
            backing_mode=ReserveFundBackingMode.ACCOUNT,
            backing_account_id=account.id,
            emergency_multiplier=6,
            user_id=user.id,
        )
    )
    session.add(
        MonthlyReadiness(
            year=2024,
            month=6,
            stage_1_done=True,
            seen_planned_ids="[]",
        )
    )
    session.add(
        YearlyPlan(
            year=2024,
            income_lines="[]",
            fixed_lines="[]",
            variable_lines="[]",
            reserves_lines="[]",
        )
    )
    session.add(
        SavedReport(
            name="Monthly spend",
            config='{"group_by":"category"}',
            user_id=user.id,
        )
    )
    session.add(
        ApiToken(
            token_hash="a" * 64,
            label="ci",
            user_id=user.id,
        )
    )
    session.add(
        AuditLog(
            # Naive datetime: AuditLog.timestamp is DateTime() without timezone
            # (TIMESTAMP WITHOUT TIME ZONE on PostgreSQL).
            timestamp=datetime(2024, 6, 1, 12, 0, 0),
            operation="INSERT",
            table_name="accounts",
            record_id=account.id,
            old_data=None,
            new_data='{"name":"Checking"}',
            reverted=False,
        )
    )
    await session.commit()
