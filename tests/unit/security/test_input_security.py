"""
Cross-cutting security tests for all input points.

Validates that:
1. SQL injection strings pass Pydantic validation as plain text and
   are stored verbatim by the ORM (parameterised queries prevent execution).
2. XSS payloads are stored verbatim (UI escaping is the final defence).
3. Oversized inputs are rejected at the schema boundary.
4. Integer fields reject non-integer injection attempts.
5. Enum fields reject unexpected string values.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.category import CategoryType
from kaleta.models.transaction import TransactionType
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.budget import BudgetCreate
from kaleta.schemas.category import CategoryCreate
from kaleta.schemas.transaction import TransactionCreate
from kaleta.services import AccountService, CategoryService, TransactionService

# ── Payload libraries ─────────────────────────────────────────────────────────

SQL_INJECTIONS = [
    "'; DROP TABLE accounts; --",
    "' OR '1'='1",
    "' OR 1=1--",
    "UNION SELECT password FROM users--",
    "1; DELETE FROM transactions WHERE 1=1",
    "' AND SLEEP(5)--",
    "'; INSERT INTO accounts (name) VALUES ('hacked')--",
    "admin'--",
    "1' ORDER BY 1--",
    "1 AND 1=2 UNION SELECT NULL--",
    "' GROUP BY columnnames having 1=1--",
    "'; exec xp_cmdshell('dir')--",
]

XSS_PAYLOADS = [
    "<script>alert('xss')</script>",
    "javascript:alert(document.cookie)",
    '"><img src=x onerror=alert(1)>',
    "<svg/onload=alert(1)>",
    "';alert(String.fromCharCode(88,83,83))//",
    "<iframe src='javascript:alert(1)'>",
    "<<SCRIPT>alert('XSS');//<</SCRIPT>",
    "<body onload=alert('XSS')>",
]

PATH_TRAVERSAL = [
    "../../../etc/passwd",
    "..\\..\\..\\windows\\system32\\cmd.exe",
    "%2e%2e%2f%2e%2e%2f",
    "....//....//etc/passwd",
]

TODAY = datetime.date.today()


# ── Schema-level: text fields accept injection strings verbatim ───────────────


class TestSchemaAcceptsPayloadsVerbatim:
    """Schemas must NOT strip or block injection strings — that is the ORM's job."""

    @pytest.mark.parametrize("payload", SQL_INJECTIONS + XSS_PAYLOADS + PATH_TRAVERSAL)
    def test_account_name_accepts_payload(self, payload: str):
        schema = AccountCreate(name=payload[:100])
        assert schema.name == payload[:100]

    @pytest.mark.parametrize("payload", SQL_INJECTIONS + XSS_PAYLOADS)
    def test_category_name_accepts_payload(self, payload: str):
        schema = CategoryCreate(name=payload[:100], type=CategoryType.EXPENSE)
        assert schema.name == payload[:100]

    @pytest.mark.parametrize("payload", SQL_INJECTIONS + XSS_PAYLOADS + PATH_TRAVERSAL)
    def test_transaction_description_accepts_payload(self, payload: str):
        schema = TransactionCreate(
            account_id=1,
            category_id=1,
            amount=Decimal("1.00"),
            type=TransactionType.EXPENSE,
            date=TODAY,
            description=payload[:500],
        )
        assert schema.description == payload[:500]


# ── Schema-level: integer fields reject string injection ──────────────────────


class TestIntegerFieldsRejectStrings:
    @pytest.mark.parametrize(
        "payload",
        [
            "1; DROP TABLE accounts",
            "' OR 1=1",
            "UNION SELECT 1",
            "../../../etc",
            "<script>",
        ],
    )
    def test_account_id_rejects_string_injection(self, payload: str):
        with pytest.raises(ValidationError):
            TransactionCreate(
                account_id=payload,  # type: ignore[arg-type]
                category_id=1,
                amount=Decimal("1.00"),
                type=TransactionType.EXPENSE,
                date=TODAY,
                description="test",
            )

    @pytest.mark.parametrize(
        "payload",
        [
            "1; DROP TABLE budgets",
            "' OR 1=1",
        ],
    )
    def test_budget_category_id_rejects_string_injection(self, payload: str):
        with pytest.raises(ValidationError):
            BudgetCreate(
                category_id=payload,  # type: ignore[arg-type]
                amount=Decimal("100.00"),
                month=1,
                year=2026,
            )


# ── Schema-level: enum fields reject unexpected strings ───────────────────────


class TestEnumFieldsRejectArbitraryStrings:
    @pytest.mark.parametrize(
        "value",
        [
            "'; DROP TABLE accounts; --",
            "admin",
            "1 OR 1=1",
            "<script>",
            "superadmin",
        ],
    )
    def test_account_type_enum_rejects_injection(self, value: str):
        with pytest.raises(ValidationError):
            AccountCreate(name="Test", type=value)  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "value",
        [
            "'; DROP TABLE categories; --",
            "transfer",  # valid for Transaction but not Category
            "<script>",
        ],
    )
    def test_category_type_enum_rejects_injection(self, value: str):
        with pytest.raises(ValidationError):
            CategoryCreate(name="Test", type=value)  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "value",
        [
            "'; DROP TABLE--",
            "payment",
            "debit",
            "<img>",
        ],
    )
    def test_transaction_type_enum_rejects_injection(self, value: str):
        with pytest.raises(ValidationError):
            TransactionCreate(
                account_id=1,
                category_id=1,
                amount=Decimal("1.00"),
                type=value,  # type: ignore[arg-type]
                date=TODAY,
                description="test",
            )


# ── Schema-level: oversized inputs rejected at boundary ──────────────────────


class TestOversizedInputsRejected:
    def test_account_name_over_100_chars(self):
        with pytest.raises(ValidationError):
            AccountCreate(name="A" * 101)

    def test_category_name_over_100_chars(self):
        with pytest.raises(ValidationError):
            CategoryCreate(name="A" * 101, type=CategoryType.EXPENSE)

    def test_transaction_description_over_500_chars(self):
        with pytest.raises(ValidationError):
            TransactionCreate(
                account_id=1,
                category_id=1,
                amount=Decimal("1.00"),
                type=TransactionType.EXPENSE,
                date=TODAY,
                description="A" * 501,
            )

    def test_budget_month_out_of_range(self):
        with pytest.raises(ValidationError):
            BudgetCreate(category_id=1, amount=Decimal("100"), month=13, year=2026)

    def test_budget_year_out_of_range(self):
        with pytest.raises(ValidationError):
            BudgetCreate(category_id=1, amount=Decimal("100"), month=1, year=1900)


# ── ORM-level: payloads stored verbatim in DB (ORM parameterises) ────────────


class TestOrmStoresPayloadsVerbatim:
    """End-to-end: write injection string → read back → must equal original."""

    @pytest.mark.parametrize("payload", SQL_INJECTIONS[:5])
    async def test_account_name_sql_injection_round_trip(self, payload: str, session: AsyncSession):
        svc = AccountService(session)
        created = await svc.create(AccountCreate(name=payload[:100]))
        fetched = await svc.get(created.id)
        assert fetched is not None
        assert fetched.name == payload[:100]

    @pytest.mark.parametrize("payload", XSS_PAYLOADS[:4])
    async def test_account_name_xss_round_trip(self, payload: str, session: AsyncSession):
        svc = AccountService(session)
        created = await svc.create(AccountCreate(name=payload[:100]))
        fetched = await svc.get(created.id)
        assert fetched is not None
        assert fetched.name == payload[:100]

    @pytest.mark.parametrize("payload", SQL_INJECTIONS[:5])
    async def test_transaction_description_sql_injection_round_trip(
        self, payload: str, session: AsyncSession
    ):
        acc_svc = AccountService(session)
        cat_svc = CategoryService(session)
        tx_svc = TransactionService(session)

        acc = await acc_svc.create(AccountCreate(name="TestAcc"))
        cat = await cat_svc.create(
            CategoryCreate(name=f"Cat-{payload[:10]}", type=CategoryType.EXPENSE)
        )

        tx = await tx_svc.create(
            TransactionCreate(
                account_id=acc.id,
                category_id=cat.id,
                amount=Decimal("1.00"),
                type=TransactionType.EXPENSE,
                date=TODAY,
                description=payload[:500],
            )
        )
        fetched = await tx_svc.get(tx.id)
        assert fetched is not None
        assert fetched.description == payload[:500]

    @pytest.mark.parametrize("payload", XSS_PAYLOADS[:4])
    async def test_category_name_xss_round_trip(self, payload: str, session: AsyncSession):
        svc = CategoryService(session)
        created = await svc.create(CategoryCreate(name=payload[:100], type=CategoryType.EXPENSE))
        fetched = await svc.get(created.id)
        assert fetched is not None
        assert fetched.name == payload[:100]
