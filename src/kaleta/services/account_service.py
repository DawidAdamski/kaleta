# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import builtins
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from kaleta.models.account import Account
from kaleta.models.import_run import ImportRun
from kaleta.models.transaction import Transaction
from kaleta.schemas.account import AccountActivityResponse, AccountCreate, AccountUpdate

# Days without a new transaction before the coverage panel marks an account stale.
STALE_ACTIVITY_DAYS = 35


class AccountService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self) -> builtins.list[Account]:
        result = await self.session.execute(
            select(Account).options(selectinload(Account.institution)).order_by(Account.name)
        )
        return list(result.scalars().all())

    async def list_with_activity(self) -> builtins.list[AccountActivityResponse]:
        """List accounts with newest transaction date and last import (no N+1)."""
        newest_tx = (
            select(
                Transaction.account_id.label("account_id"),
                func.max(Transaction.date).label("newest_date"),
            )
            .group_by(Transaction.account_id)
            .subquery()
        )
        ranked_imports = (
            select(
                ImportRun.account_id.label("account_id"),
                ImportRun.created_at.label("last_import_at"),
                ImportRun.filename.label("last_import_filename"),
                func.row_number()
                .over(
                    partition_by=ImportRun.account_id,
                    order_by=ImportRun.created_at.desc(),
                )
                .label("rn"),
            )
        ).subquery()
        last_import = (
            select(
                ranked_imports.c.account_id,
                ranked_imports.c.last_import_at,
                ranked_imports.c.last_import_filename,
            )
            .where(ranked_imports.c.rn == 1)
            .subquery()
        )

        result = await self.session.execute(
            select(
                Account,
                newest_tx.c.newest_date,
                last_import.c.last_import_at,
                last_import.c.last_import_filename,
            )
            .options(selectinload(Account.institution))
            .outerjoin(newest_tx, Account.id == newest_tx.c.account_id)
            .outerjoin(last_import, Account.id == last_import.c.account_id)
            .order_by(Account.name)
        )

        rows: builtins.list[AccountActivityResponse] = []
        for account, newest_date, last_at, last_filename in result.all():
            base = AccountActivityResponse.model_validate(account)
            rows.append(
                base.model_copy(
                    update={
                        "newest_transaction_date": newest_date,
                        "last_import_at": last_at,
                        "last_import_filename": last_filename,
                    }
                )
            )
        return rows

    async def get(self, account_id: int) -> Account | None:
        result = await self.session.execute(
            select(Account)
            .options(selectinload(Account.institution))
            .where(Account.id == account_id)
        )
        return result.scalar_one_or_none()

    async def create(self, data: AccountCreate) -> Account:
        account = Account(**data.model_dump())
        self.session.add(account)
        await self.session.commit()
        await self.session.refresh(account)
        return account

    async def update(self, account_id: int, data: AccountUpdate) -> Account | None:
        account = await self.get(account_id)
        if account is None:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(account, field, value)
        await self.session.commit()
        await self.session.refresh(account)
        return account

    async def delete(self, account_id: int) -> bool:
        account = await self.get(account_id)
        if account is None:
            return False
        await self.session.delete(account)
        await self.session.commit()
        return True

    async def find_by_external_number(self, digits: str) -> Account | None:
        """Find account whose ``external_account_number`` ends with the given digit string."""
        result = await self.session.execute(
            select(Account)
            .options(selectinload(Account.institution))
            .where(Account.external_account_number.ilike(f"%{digits}"))
        )
        return result.scalar_one_or_none()

    async def save_external_number(self, account_id: int, number: str) -> None:
        """Persist the last-10-digits of an external account number for auto-matching."""
        account = await self.get(account_id)
        if account is not None:
            account.external_account_number = number[-10:]
            await self.session.commit()

    async def adjust_balance(self, account_id: int, delta: Decimal) -> None:
        account = await self.get(account_id)
        if account is not None:
            account.balance += delta
            await self.session.commit()

    @staticmethod
    def is_stale(newest_transaction_date: date | None, *, today: date | None = None) -> bool:
        """True when the account has activity older than ``STALE_ACTIVITY_DAYS`` (or none)."""
        if newest_transaction_date is None:
            return True
        ref = today or date.today()
        return (ref - newest_transaction_date).days > STALE_ACTIVITY_DAYS
