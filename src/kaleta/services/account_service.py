# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import builtins
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import ColumnElement, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from kaleta.db.types import ACCOUNT_SUFFIX_DIGITS, account_suffix_index, digits_only
from kaleta.exceptions import ConflictError
from kaleta.models.account import Account
from kaleta.models.import_run import ImportRun
from kaleta.models.transaction import Transaction, TransactionType, TransferDirection
from kaleta.schemas.account import (
    AccountActivityResponse,
    AccountCreate,
    AccountResponse,
    AccountUpdate,
)
from kaleta.services.text_order import by_name, text_key

# Days without a new transaction before the coverage panel marks an account stale.
STALE_ACTIVITY_DAYS = 35

_CENT = Decimal("0.01")


def signed_ledger_amount() -> ColumnElement[Decimal]:
    """What one transaction row does to its account's balance, as SQL.

    ``amount`` is unsigned: an income adds it, an expense takes it away, and
    a transfer leg does either according to its ``transfer_direction``.
    """
    return case(
        (Transaction.type == TransactionType.INCOME, Transaction.amount),
        (Transaction.type == TransactionType.EXPENSE, -Transaction.amount),
        (Transaction.transfer_direction == TransferDirection.IN, Transaction.amount),
        (Transaction.transfer_direction == TransferDirection.OUT, -Transaction.amount),
        else_=Decimal("0"),
    )


@dataclass(frozen=True)
class BalanceBreakdown:
    """The accounts a total is worth naming, and what the rest add up to."""

    shown: builtins.list[AccountResponse]
    hidden_count: int
    hidden_total: Decimal


class AccountService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self) -> builtins.list[Account]:
        result = await self.session.execute(
            select(Account).options(selectinload(Account.institution))
        )
        return by_name(result.scalars().all())

    async def balance_breakdown(self, limit: int = 3) -> BalanceBreakdown:
        """The *limit* largest accounts, plus how many and how much they omit.

        A card that shows a grand total next to a handful of accounts has to
        say what it left out, or the figures read as a breakdown that does not
        add up. Ranked by *size*, not by signed balance and not by name: a
        credit card at -4 000 moves the total as much as a savings account at
        +4 000, so hiding it among "N more" would explain the least about the
        figure it sits under.
        """
        accounts = sorted(await self.list_responses(), key=lambda a: abs(a.balance), reverse=True)
        shown, rest = accounts[:limit], accounts[limit:]
        return BalanceBreakdown(
            shown=shown,
            hidden_count=len(rest),
            hidden_total=sum((a.balance for a in rest), start=Decimal("0")),
        )

    async def ledger_sums(
        self,
        account_ids: builtins.list[int] | None = None,
        *,
        as_of: date | None = None,
    ) -> dict[int, Decimal]:
        """Signed sum of each account's transactions; accounts with none are absent."""
        stmt = select(
            Transaction.account_id, func.coalesce(func.sum(signed_ledger_amount()), 0)
        ).group_by(Transaction.account_id)
        if account_ids is not None:
            stmt = stmt.where(Transaction.account_id.in_(account_ids))
        if as_of is not None:
            stmt = stmt.where(Transaction.date <= as_of)
        result = await self.session.execute(stmt)
        return {
            int(account_id): Decimal(str(total)).quantize(_CENT)
            for account_id, total in result.all()
        }

    async def balances(
        self,
        account_ids: builtins.list[int] | None = None,
        *,
        as_of: date | None = None,
    ) -> dict[int, Decimal]:
        """Current balance of each account: opening balance + signed ledger.

        The one place a balance comes from. Every row counts, whatever its
        date, unless ``as_of`` cuts the ledger off at that day (inclusive).
        Two queries whatever the number of accounts.
        """
        stmt = select(Account.id, Account.opening_balance)
        if account_ids is not None:
            stmt = stmt.where(Account.id.in_(account_ids))
        openings = (await self.session.execute(stmt)).all()
        sums = await self.ledger_sums(account_ids, as_of=as_of)
        return {
            int(account_id): (Decimal(opening) + sums.get(int(account_id), Decimal("0"))).quantize(
                _CENT
            )
            for account_id, opening in openings
        }

    async def balance(self, account_id: int, *, as_of: date | None = None) -> Decimal:
        """One account's balance; zero for an account that does not exist."""
        return (await self.balances([account_id], as_of=as_of)).get(account_id, Decimal("0.00"))

    @staticmethod
    def edited_balance(opened: Decimal, entered: float | Decimal | None) -> Decimal | None:
        """The balance an edit form should send, or ``None`` to leave it alone.

        Only a figure the user actually changed is sent: resending the one
        the form opened with would pin the balance to it even if a
        transaction landed while the form was open.
        """
        if entered is None:
            return None
        value = Decimal(str(entered)).quantize(_CENT)
        return None if value == opened else value

    async def list_responses(self) -> builtins.list[AccountResponse]:
        """Every account with its derived balance, ordered by name."""
        accounts = await self.list()
        balances = await self.balances()
        return [AccountResponse.from_account(a, balances[a.id]) for a in accounts]

    async def get_response(self, account_id: int) -> AccountResponse | None:
        account = await self.get(account_id)
        if account is None:
            return None
        return AccountResponse.from_account(account, await self.balance(account_id))

    async def get_activity_row(self, account_id: int) -> AccountActivityResponse | None:
        """One account as the accounts page lists it (balance, no coverage fields)."""
        account = await self.get(account_id)
        if account is None:
            return None
        return AccountActivityResponse.from_account(account, await self.balance(account_id))

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
        )

        balances = await self.balances()
        rows: builtins.list[AccountActivityResponse] = []
        ordered = sorted(result.all(), key=lambda row: text_key(row[0].name))
        for account, newest_date, last_at, last_filename in ordered:
            rows.append(
                AccountActivityResponse.from_account(
                    account,
                    balances[account.id],
                    newest_transaction_date=newest_date,
                    last_import_at=last_at,
                    last_import_filename=last_filename,
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
        values = data.model_dump(exclude={"balance"})
        account = Account(**values, opening_balance=data.balance)
        self.session.add(account)
        await self.session.commit()
        await self.session.refresh(account)
        return account

    async def update(self, account_id: int, data: AccountUpdate) -> Account | None:
        account = await self.get(account_id)
        if account is None:
            return None
        updates = data.model_dump(exclude_unset=True, exclude={"balance"})
        for field, value in updates.items():
            setattr(account, field, value)
        if data.balance is not None:
            ledger = (await self.ledger_sums([account_id])).get(account_id, Decimal("0"))
            account.opening_balance = data.balance - ledger
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
        """Find account whose ``external_account_number`` ends with the given digit string.

        The number is encrypted, so the candidates are the accounts sharing the
        blind index of its last ``ACCOUNT_SUFFIX_DIGITS`` digits (ADR-20), and
        "ends with" is checked on the decrypted numbers.
        """
        wanted = digits_only(digits)
        if len(wanted) < ACCOUNT_SUFFIX_DIGITS:
            return None
        result = await self.session.execute(
            select(Account)
            .options(selectinload(Account.institution))
            .where(Account.external_account_number_sfx_bidx == account_suffix_index(wanted))
            .order_by(Account.id)
        )
        matches = [
            account
            for account in result.scalars().all()
            if digits_only(account.external_account_number or "").endswith(wanted)
        ]
        if len(matches) > 1:
            msg = "More than one account matches that account number."
            raise ConflictError(msg)
        return matches[0] if matches else None

    async def save_external_number(self, account_id: int, number: str) -> None:
        """Persist the last-10-digits of an external account number for auto-matching."""
        account = await self.get(account_id)
        if account is not None:
            account.external_account_number = number[-10:]
            await self.session.commit()

    @staticmethod
    def is_stale(newest_transaction_date: date | None, *, today: date | None = None) -> bool:
        """True when the account has activity older than ``STALE_ACTIVITY_DAYS`` (or none)."""
        if newest_transaction_date is None:
            return True
        ref = today or date.today()
        return (ref - newest_transaction_date).days > STALE_ACTIVITY_DAYS
