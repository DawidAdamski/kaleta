from __future__ import annotations

import datetime
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from kaleta.models.account import Account, AccountType
from kaleta.models.asset import Asset
from kaleta.models.transaction import Transaction, TransactionType


@dataclass
class AccountSnapshot:
    id: int
    name: str
    type: AccountType
    institution_name: str | None
    balance: Decimal

    @property
    def is_asset(self) -> bool:
        return self.balance >= 0

    @property
    def asset_value(self) -> Decimal:
        return self.balance if self.balance > 0 else Decimal("0")

    @property
    def liability_value(self) -> Decimal:
        return -self.balance if self.balance < 0 else Decimal("0")


@dataclass
class MonthlyNetWorth:
    year: int
    month: int
    net_worth: Decimal

    @property
    def label(self) -> str:
        return datetime.date(self.year, self.month, 1).strftime("%b %Y")


@dataclass
class PhysicalAssetSnapshot:
    id: int
    name: str
    type: str
    value: Decimal
    description: str


@dataclass
class NetWorthSummary:
    accounts: list[AccountSnapshot]
    physical_assets: list[PhysicalAssetSnapshot]
    history: list[MonthlyNetWorth]
    prev_month_net_worth: Decimal | None

    @property
    def total_physical_assets(self) -> Decimal:
        return sum((a.value for a in self.physical_assets), Decimal("0"))

    @property
    def total_assets(self) -> Decimal:
        account_assets = sum((a.asset_value for a in self.accounts), Decimal("0"))
        return account_assets + self.total_physical_assets

    @property
    def total_liabilities(self) -> Decimal:
        return sum((a.liability_value for a in self.accounts), Decimal("0"))

    @property
    def net_worth(self) -> Decimal:
        return self.total_assets - self.total_liabilities

    @property
    def monthly_change(self) -> Decimal | None:
        if self.prev_month_net_worth is None:
            return None
        return self.net_worth - self.prev_month_net_worth


class NetWorthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_summary(self, history_months: int = 13) -> NetWorthSummary:
        accounts = await self._load_accounts()
        physical_assets = await self._load_physical_assets()
        history = await self._monthly_history(accounts, physical_assets, history_months)

        prev = history[-2].net_worth if len(history) >= 2 else None
        return NetWorthSummary(
            accounts=accounts,
            physical_assets=physical_assets,
            history=history,
            prev_month_net_worth=prev,
        )

    async def _load_physical_assets(self) -> list[PhysicalAssetSnapshot]:
        result = await self.session.execute(select(Asset).order_by(Asset.name))
        return [
            PhysicalAssetSnapshot(
                id=a.id,
                name=a.name,
                type=a.type.value,
                value=a.value,
                description=a.description,
            )
            for a in result.scalars().all()
        ]

    async def _load_accounts(self) -> list[AccountSnapshot]:
        result = await self.session.execute(
            select(Account).options(selectinload(Account.institution)).order_by(Account.name)
        )
        return [
            AccountSnapshot(
                id=a.id,
                name=a.name,
                type=a.type,
                institution_name=a.institution.name if a.institution else None,
                balance=a.balance,
            )
            for a in result.scalars().all()
        ]

    async def _monthly_history(
        self,
        accounts: list[AccountSnapshot],
        physical_assets: list[PhysicalAssetSnapshot],
        months: int,
    ) -> list[MonthlyNetWorth]:
        today = datetime.date.today()
        physical_total = sum((a.value for a in physical_assets), Decimal("0"))
        current_net_worth = sum((a.balance for a in accounts), Decimal("0")) + physical_total

        # Monthly net income/expense (excluding internal transfers and pure transfers)
        result = await self.session.execute(
            select(
                func.strftime("%Y", Transaction.date).label("year"),
                func.strftime("%m", Transaction.date).label("month"),
                Transaction.type,
                func.sum(Transaction.amount).label("total"),
            )
            .where(
                Transaction.is_internal_transfer == False,  # noqa: E712
                Transaction.type.in_([TransactionType.INCOME, TransactionType.EXPENSE]),
            )
            .group_by("year", "month", Transaction.type)
        )

        # Build (year, month) -> net_change map
        monthly_net: dict[tuple[int, int], Decimal] = {}
        for row in result:
            key = (int(row.year), int(row.month))
            delta = row.total if row.type == TransactionType.INCOME else -row.total
            monthly_net[key] = monthly_net.get(key, Decimal("0")) + delta

        # Walk backwards from current month, inserting at front
        snapshots: list[MonthlyNetWorth] = []
        running = current_net_worth
        for i in range(months):
            total = today.year * 12 + today.month - 1 - i
            y, m = total // 12, total % 12 + 1
            snapshots.insert(0, MonthlyNetWorth(year=y, month=m, net_worth=running))
            running -= monthly_net.get((y, m), Decimal("0"))

        return snapshots
