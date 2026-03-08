from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from kaleta.models.account import Account, AccountType
from kaleta.models.asset import Asset
from kaleta.models.transaction import Transaction, TransactionType
from kaleta.services.currency_rate_service import CurrencyRateService


@dataclass
class AccountSnapshot:
    id: int
    name: str
    type: AccountType
    institution_name: str | None
    balance: Decimal
    currency: str = "PLN"
    # balance converted to default currency using historical rates from DB
    balance_in_default: Decimal = field(default=Decimal("0"))
    rate_known: bool = True  # False when no rate was found in DB (fell back to 1:1)

    @property
    def is_asset(self) -> bool:
        return self.balance_in_default >= 0

    @property
    def asset_value(self) -> Decimal:
        return self.balance_in_default if self.balance_in_default > 0 else Decimal("0")

    @property
    def liability_value(self) -> Decimal:
        return -self.balance_in_default if self.balance_in_default < 0 else Decimal("0")


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
    default_currency: str = "PLN"

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

    @property
    def has_unknown_rates(self) -> bool:
        """True if any foreign-currency account has no known exchange rate."""
        return any(
            not a.rate_known and a.currency != self.default_currency
            for a in self.accounts
        )


class NetWorthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._rate_svc = CurrencyRateService(session)

    async def get_summary(
        self,
        history_months: int = 13,
        default_currency: str = "PLN",
    ) -> NetWorthSummary:
        today = datetime.date.today()
        accounts_raw = await self._load_accounts_raw()
        physical_assets = await self._load_physical_assets()

        # Determine which foreign currencies we need rates for
        foreign_currencies = {
            a.currency for a in accounts_raw if a.currency != default_currency
        }

        # Load full rate history for batch lookups
        rate_history = await self._rate_svc.load_rates_for_currencies(
            foreign_currencies, default_currency
        )

        # Build current account snapshots using today's rate
        accounts = self._apply_rates(
            accounts_raw, rate_history, today, default_currency
        )

        history = await self._monthly_history(
            accounts_raw, rate_history, physical_assets, history_months, default_currency
        )

        prev = history[-2].net_worth if len(history) >= 2 else None
        return NetWorthSummary(
            accounts=accounts,
            physical_assets=physical_assets,
            history=history,
            prev_month_net_worth=prev,
            default_currency=default_currency,
        )

    def _apply_rates(
        self,
        accounts_raw: list[Account],
        rate_history: dict[str, list[tuple[datetime.date, Decimal]]],
        on_date: datetime.date,
        default_currency: str,
    ) -> list[AccountSnapshot]:
        snapshots = []
        for a in accounts_raw:
            if a.currency == default_currency:
                rate = Decimal("1")
                known = True
            else:
                rate = _nearest_rate(rate_history.get(a.currency, []), on_date)
                known = rate is not None
                if rate is None:
                    rate = Decimal("1")  # fallback
            snapshots.append(
                AccountSnapshot(
                    id=a.id,
                    name=a.name,
                    type=a.type,
                    institution_name=a.institution.name if a.institution else None,
                    balance=a.balance,
                    currency=a.currency,
                    balance_in_default=a.balance * rate,
                    rate_known=known,
                )
            )
        return snapshots

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

    async def _load_accounts_raw(self) -> list[Account]:
        result = await self.session.execute(
            select(Account).options(selectinload(Account.institution)).order_by(Account.name)
        )
        return list(result.scalars().all())

    async def _monthly_history(
        self,
        accounts_raw: list[Account],
        rate_history: dict[str, list[tuple[datetime.date, Decimal]]],
        physical_assets: list[PhysicalAssetSnapshot],
        months: int,
        default_currency: str,
    ) -> list[MonthlyNetWorth]:
        today = datetime.date.today()
        physical_total = sum((a.value for a in physical_assets), Decimal("0"))

        # Current account balances in default currency (using today's rates)
        current_account_total = sum(
            a.balance * (
                _nearest_rate(rate_history.get(a.currency, []), today) or Decimal("1")
                if a.currency != default_currency else Decimal("1")
            )
            for a in accounts_raw
        )
        current_net_worth = current_account_total + physical_total

        # Monthly net income/expense (excluding internal transfers)
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

        monthly_net: dict[tuple[int, int], Decimal] = {}
        for row in result:
            key = (int(row.year), int(row.month))
            delta = row.total if row.type == TransactionType.INCOME else -row.total
            monthly_net[key] = monthly_net.get(key, Decimal("0")) + delta

        # Walk backwards, using the rate valid at each month's end date
        snapshots: list[MonthlyNetWorth] = []
        running = current_net_worth
        for i in range(months):
            total = today.year * 12 + today.month - 1 - i
            y, m = total // 12, total % 12 + 1
            snapshots.insert(0, MonthlyNetWorth(year=y, month=m, net_worth=running))
            running -= monthly_net.get((y, m), Decimal("0"))

        return snapshots


def _nearest_rate(
    entries: list[tuple[datetime.date, Decimal]],
    on_date: datetime.date,
) -> Decimal | None:
    """
    Binary-search sorted list of (date, rate) pairs for the most recent entry
    on or before `on_date`. Returns None if no entry qualifies.
    """
    if not entries:
        return None
    lo, hi = 0, len(entries) - 1
    best: Decimal | None = None
    while lo <= hi:
        mid = (lo + hi) // 2
        d, r = entries[mid]
        if d <= on_date:
            best = r
            lo = mid + 1
        else:
            hi = mid - 1
    return best
