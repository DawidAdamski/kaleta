# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared seed helpers for e2e tests.

All helpers write to the isolated e2e database via the ephemeral app's REST
API (configured by ``tests/e2e/conftest.py``). Direct DB access uses the same
URL via ``configure(..., db_url=...)``.
"""

from __future__ import annotations

import datetime
from typing import Any

import httpx

API_BASE = "http://127.0.0.1:8081/api/v1"
_client = httpx.Client(timeout=10.0)


def configure(base_url: str, *, db_url: str | None = None, api_token: str | None = None) -> None:
    """Point helpers at the active e2e Kaleta instance."""
    global API_BASE, _client
    API_BASE = f"{base_url.rstrip('/')}/api/v1"
    headers: dict[str, str] = {}
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"
    _client = httpx.Client(timeout=10.0, base_url=base_url.rstrip("/"), headers=headers)

    if db_url is not None:
        from kaleta.db import configure_database

        configure_database(db_url, debug=True)


def seed_account(name: str, currency: str = "PLN", institution_id: int | None = None) -> int:
    """Create an account; return its ID."""
    body: dict[str, Any] = {
        "name": name,
        "currency": currency,
        "type": "checking",
        "balance": "0.00",
    }
    if institution_id is not None:
        body["institution_id"] = institution_id
    resp = _client.post(f"{API_BASE}/accounts/", json=body)
    resp.raise_for_status()
    return resp.json()["id"]


def seed_institution(name: str) -> int:
    """Create an institution; return its ID."""
    resp = _client.post(
        f"{API_BASE}/institutions/",
        json={"name": name, "type": "bank"},
    )
    resp.raise_for_status()
    return resp.json()["id"]


def seed_category(name: str, cat_type: str = "expense", parent_id: int | None = None) -> int:
    """Create a category; return its ID."""
    body: dict[str, Any] = {"name": name, "type": cat_type}
    if parent_id is not None:
        body["parent_id"] = parent_id
    resp = _client.post(f"{API_BASE}/categories/", json=body)
    resp.raise_for_status()
    return resp.json()["id"]


def get_or_seed_category(name: str, cat_type: str = "expense") -> int:
    """Return an existing category id by name, or create it."""
    resp = _client.get(f"{API_BASE}/categories/", params={"type": cat_type})
    resp.raise_for_status()
    for cat in resp.json():
        if cat.get("name") == name and cat.get("parent_id") is None:
            return int(cat["id"])
        for child in cat.get("children") or []:
            if child.get("name") == name:
                return int(child["id"])
    return seed_category(name, cat_type=cat_type)


def seed_payee(name: str) -> int:
    """Create a payee; return its ID."""
    resp = _client.post(f"{API_BASE}/payees/", json={"name": name})
    resp.raise_for_status()
    return resp.json()["id"]


def seed_rule(pattern: str, category_id: int, *, priority: int = 0) -> int:
    """Create a categorisation rule via the service layer; return its ID."""
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    from kaleta.db import AsyncSessionFactory
    from kaleta.schemas.categorisation_rule import CategorisationRuleCreate
    from kaleta.services import RuleService

    def _worker() -> int:
        async def _create() -> int:
            async with AsyncSessionFactory() as session:
                rule = await RuleService(session).create(
                    CategorisationRuleCreate(
                        pattern=pattern,
                        category_id=category_id,
                        priority=priority,
                    )
                )
                return rule.id

        return asyncio.run(_create())

    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(_worker).result()


def seed_import_rule(
    filename_pattern: str,
    account_id: int,
    *,
    column_mapping: dict[str, Any] | None = None,
    is_active: bool = True,
) -> int:
    """Create a filename-pattern import rule via the REST API; return its ID."""
    body: dict[str, Any] = {
        "filename_pattern": filename_pattern,
        "account_id": account_id,
        "column_mapping": column_mapping or {"date": 0, "amount": 1, "description": 2},
        "is_active": is_active,
    }
    resp = _client.post(f"{API_BASE}/import-rules/", json=body)
    resp.raise_for_status()
    return int(resp.json()["id"])


def update_import_rule(rule_id: int, **fields: Any) -> None:
    """PATCH-like update of an import rule via PUT."""
    resp = _client.put(f"{API_BASE}/import-rules/{rule_id}", json=fields)
    resp.raise_for_status()


def list_import_rules() -> list[dict[str, Any]]:
    """Return all saved import rules."""
    resp = _client.get(f"{API_BASE}/import-rules/")
    resp.raise_for_status()
    return list(resp.json())


def seed_transaction(
    account_id: int,
    category_id: int,
    amount: float,
    tx_type: str = "expense",
    date: datetime.date | None = None,
    description: str = "seed",
    payee_id: int | None = None,
    notes: str | None = None,
) -> int:
    """Create a single transaction; returns its ID."""
    body: dict[str, Any] = {
        "account_id": account_id,
        "category_id": category_id,
        "amount": str(amount),
        "type": tx_type,
        "date": str(date or datetime.date.today()),
        "description": description,
    }
    if payee_id is not None:
        body["payee_id"] = payee_id
    if notes is not None:
        body["notes"] = notes
    resp = _client.post(f"{API_BASE}/transactions/", json=body)
    resp.raise_for_status()
    return resp.json()["id"]


def seed_budget(category_id: int, amount: float, month: int, year: int) -> int:
    """Create a budget entry; return its ID."""
    body = {
        "category_id": category_id,
        "amount": str(amount),
        "month": month,
        "year": year,
    }
    resp = _client.post(f"{API_BASE}/budgets/", json=body)
    resp.raise_for_status()
    return resp.json()["id"]


def seed_many_transactions(
    account_id: int,
    category_id: int,
    n_days: int = 90,
    amount: float = 50.0,
) -> None:
    """Seed one expense transaction per day for the past n_days days."""
    today = datetime.date.today()
    for i in range(n_days):
        d = today - datetime.timedelta(days=i)
        seed_transaction(account_id, category_id, amount, date=d)


def update_account(account_id: int, **fields: Any) -> dict:
    """PATCH-style update via PUT; only supplied fields are changed."""
    resp = _client.put(f"{API_BASE}/accounts/{account_id}", json=fields)
    resp.raise_for_status()
    return resp.json()


def seed_account_with_external(
    name: str,
    external_account_number: str,
    currency: str = "PLN",
) -> int:
    """Create an account and set its external account number."""
    account_id = seed_account(name, currency=currency)
    update_account(account_id, external_account_number=external_account_number)
    return account_id


def seed_income_category(name: str, parent_id: int | None = None) -> int:
    """Create a top-level income category; return its ID."""
    return seed_category(name, cat_type="income", parent_id=parent_id)


def seed_planned_transaction(
    name: str,
    amount: float,
    account_id: int,
    frequency: str = "monthly",
    tx_type: str = "expense",
    category_id: int | None = None,
    is_active: bool = True,
    start_date: datetime.date | None = None,
) -> int:
    """Create a planned transaction via the service layer; return its ID.

    Runs in a worker thread so ``asyncio.run`` is not invoked from pytest-
    playwright's already-running event loop.
    """
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    from decimal import Decimal

    from kaleta.db import AsyncSessionFactory
    from kaleta.models.planned_transaction import RecurrenceFrequency
    from kaleta.models.transaction import TransactionType
    from kaleta.schemas.planned_transaction import PlannedTransactionCreate
    from kaleta.services import PlannedTransactionService

    def _worker() -> int:
        async def _create() -> int:
            async with AsyncSessionFactory() as session:
                svc = PlannedTransactionService(session)
                pt = await svc.create(
                    PlannedTransactionCreate(
                        name=name,
                        amount=Decimal(str(amount)),
                        type=TransactionType(tx_type),
                        account_id=account_id,
                        category_id=category_id,
                        frequency=RecurrenceFrequency(frequency),
                        start_date=start_date or datetime.date.today(),
                        is_active=is_active,
                    )
                )
                return pt.id

        return asyncio.run(_create())

    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(_worker).result()


def _run_async_worker(coro_factory):  # noqa: ANN001
    """Run an async coroutine factory in a worker thread (pytest-playwright safe)."""
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    def _worker() -> Any:
        return asyncio.run(coro_factory())

    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(_worker).result()


def seed_subscription(
    name: str,
    amount: float,
    cadence_days: int = 30,
    *,
    payee_id: int | None = None,
    next_expected_at: datetime.date | None = None,
) -> int:
    """Create a subscription via the service layer; return its ID."""
    from decimal import Decimal

    from kaleta.db import AsyncSessionFactory
    from kaleta.schemas.subscription import SubscriptionCreate
    from kaleta.services import SubscriptionService

    async def _create() -> int:
        async with AsyncSessionFactory() as session:
            sub = await SubscriptionService(session).create(
                SubscriptionCreate(
                    name=name,
                    amount=Decimal(str(amount)),
                    cadence_days=cadence_days,
                    payee_id=payee_id,
                    first_seen_at=datetime.date.today(),
                    next_expected_at=next_expected_at,
                )
            )
            return sub.id

    return _run_async_worker(_create)


def seed_recurring_payee_charges(
    account_id: int,
    category_id: int,
    payee_name: str,
    amount: float,
    *,
    months: int = 3,
    interval_days: int = 30,
) -> int:
    """Seed a payee with recurring monthly-like charges for the subscription detector."""
    payee_id = seed_payee(payee_name)
    today = datetime.date.today()
    for i in range(months):
        tx_date = today - datetime.timedelta(days=interval_days * i)
        seed_transaction(
            account_id,
            category_id,
            amount,
            date=tx_date,
            description=f"{payee_name} charge",
            payee_id=payee_id,
        )
    return payee_id


def seed_personal_loan(
    counterparty: str,
    principal: float,
    *,
    direction: str = "outgoing",
    opened_at: datetime.date | None = None,
    due_at: datetime.date | None = None,
) -> int:
    """Create a personal loan via the service layer; return its ID."""
    from decimal import Decimal

    from kaleta.db import AsyncSessionFactory
    from kaleta.models.personal_loan import LoanDirection
    from kaleta.schemas.personal_loan import PersonalLoanCreate
    from kaleta.services import PersonalLoanService

    async def _create() -> int:
        async with AsyncSessionFactory() as session:
            svc = PersonalLoanService(session)
            cp = await svc.upsert_counterparty(counterparty)
            loan = await svc.create_loan(
                PersonalLoanCreate(
                    counterparty_id=cp.id,
                    direction=LoanDirection(direction),
                    principal=Decimal(str(principal)),
                    currency="PLN",
                    opened_at=opened_at or datetime.date.today(),
                    due_at=due_at,
                )
            )
            return loan.id

    return _run_async_worker(_create)


def seed_reserve_fund(
    name: str,
    target_amount: float,
    backing_account_id: int,
    *,
    kind: str = "emergency",
    emergency_multiplier: int | None = 3,
) -> int:
    """Create a reserve fund via the service layer; return its ID."""
    from decimal import Decimal

    from kaleta.db import AsyncSessionFactory
    from kaleta.models.reserve_fund import ReserveFundBackingMode, ReserveFundKind
    from kaleta.schemas.reserve_fund import ReserveFundCreate
    from kaleta.services import ReserveFundService

    async def _create() -> int:
        async with AsyncSessionFactory() as session:
            fund = await ReserveFundService(session).create(
                ReserveFundCreate(
                    name=name,
                    kind=ReserveFundKind(kind),
                    target_amount=Decimal(str(target_amount)),
                    backing_mode=ReserveFundBackingMode.ACCOUNT,
                    backing_account_id=backing_account_id,
                    emergency_multiplier=emergency_multiplier,
                )
            )
            return fund.id

    return _run_async_worker(_create)
