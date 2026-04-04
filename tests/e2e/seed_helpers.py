"""Shared seed helpers for e2e tests.

All helpers seed data via the app's REST API so that data lands in whichever
SQLite file the running app is configured to use — regardless of the CWD.
"""

from __future__ import annotations

import datetime
from typing import Any

import httpx

API_BASE = "http://localhost:8080/api/v1"

_client = httpx.Client(timeout=10.0)


def _get_or_post(list_url: str, match_field: str, match_value: Any, post_body: dict) -> dict:
    """Return an existing record matching ``match_value`` or POST to create it."""
    resp = _client.get(list_url)
    resp.raise_for_status()
    records = resp.json()
    for r in records:
        if r.get(match_field) == match_value:
            return r
    resp = _client.post(list_url, json=post_body)
    resp.raise_for_status()
    return resp.json()


def seed_account(name: str, currency: str = "PLN") -> int:
    """Get or create an account by name; return its ID."""
    rec = _get_or_post(
        f"{API_BASE}/accounts/",
        "name",
        name,
        {"name": name, "currency": currency, "type": "checking", "balance": "0.00"},
    )
    return rec["id"]


def seed_institution(name: str) -> int:
    """Get or create an institution by name; return its ID."""
    rec = _get_or_post(
        f"{API_BASE}/institutions/",
        "name",
        name,
        {"name": name, "type": "bank"},
    )
    return rec["id"]


def seed_category(name: str, cat_type: str = "expense", parent_id: int | None = None) -> int:
    """Get or create a top-level category by name; return its ID."""
    resp = _client.get(f"{API_BASE}/categories/")
    resp.raise_for_status()
    records = resp.json()
    for r in records:
        if r.get("name") == name and r.get("parent_id") == parent_id:
            return r["id"]
    body: dict = {"name": name, "type": cat_type}
    if parent_id is not None:
        body["parent_id"] = parent_id
    resp = _client.post(f"{API_BASE}/categories/", json=body)
    resp.raise_for_status()
    return resp.json()["id"]


def seed_transaction(
    account_id: int,
    category_id: int,
    amount: float,
    tx_type: str = "expense",
    date: datetime.date | None = None,
    description: str = "seed",
) -> int:
    """Create a single transaction; returns its ID."""
    body = {
        "account_id": account_id,
        "category_id": category_id,
        "amount": str(amount),
        "type": tx_type,
        "date": str(date or datetime.date.today()),
        "description": description,
    }
    resp = _client.post(f"{API_BASE}/transactions/", json=body)
    resp.raise_for_status()
    return resp.json()["id"]


def seed_budget(category_id: int, amount: float, month: int, year: int) -> int:
    """Upsert a budget entry; return its ID."""
    resp = _client.get(f"{API_BASE}/budgets/?year={year}&month={month}")
    resp.raise_for_status()
    for b in resp.json():
        if (
            b.get("category_id") == category_id
            and b.get("month") == month
            and b.get("year") == year
        ):
            return b["id"]
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
    resp = _client.get(f"{API_BASE}/transactions/?account_id={account_id}&limit=1000")
    resp.raise_for_status()
    existing_dates = {t["date"] for t in resp.json() if t.get("description") == "seed"}

    today = datetime.date.today()
    for i in range(n_days):
        d = today - datetime.timedelta(days=i)
        if str(d) in existing_dates:
            continue
        seed_transaction(account_id, category_id, amount, date=d)


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
    """Get or create a planned transaction by name; return its ID.

    The planned transactions API is not exposed via REST, so we use the service
    layer running in a background thread.
    """
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    from decimal import Decimal

    from sqlalchemy import select

    def _worker() -> int:
        # Point AsyncSessionFactory at the app's DB
        import httpx as _httpx

        from kaleta.db import AsyncSessionFactory
        from kaleta.models.planned_transaction import PlannedTransaction, RecurrenceFrequency
        from kaleta.models.transaction import TransactionType
        from kaleta.schemas.planned_transaction import PlannedTransactionCreate
        from kaleta.services import PlannedTransactionService

        resp = _httpx.get("http://localhost:8080/api/v1/accounts/")
        resp.raise_for_status()

        async def _create() -> int:
            async with AsyncSessionFactory() as session:
                existing = (
                    await session.execute(
                        select(PlannedTransaction).where(PlannedTransaction.name == name)
                    )
                ).scalar_one_or_none()
                if existing:
                    return existing.id
                svc = PlannedTransactionService(session)
                payload = PlannedTransactionCreate(
                    name=name,
                    amount=Decimal(str(amount)),
                    type=TransactionType(tx_type),
                    account_id=account_id,
                    category_id=category_id,
                    frequency=RecurrenceFrequency(frequency),
                    start_date=start_date or datetime.date.today(),
                    is_active=is_active,
                )
                pt = await svc.create(payload)
                return pt.id

        return asyncio.run(_create())

    with ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(_worker).result()
