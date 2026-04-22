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

# Account-type → asset/liability bucket. See plan net-worth-layout-refresh.
_LIABILITY_TYPES: frozenset[AccountType] = frozenset({AccountType.CREDIT})


def is_liability_kind(account_type: AccountType) -> bool:
    return account_type in _LIABILITY_TYPES


def is_asset_kind(account_type: AccountType) -> bool:
    return account_type not in _LIABILITY_TYPES


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
        """Kind-based classification: checking/savings/cash → asset, credit → liability.

        Overdrawn asset-kind accounts (e.g. checking with negative balance) still
        count as assets — the negative value is reflected in the Assets total.
        """
        return is_asset_kind(self.type)

    @property
    def asset_value(self) -> Decimal:
        return self.balance_in_default if self.is_asset else Decimal("0")

    @property
    def liability_value(self) -> Decimal:
        """Liabilities are displayed as positive numbers (the amount owed)."""
        return -self.balance_in_default if not self.is_asset else Decimal("0")


@dataclass
class MonthlyNetWorth:
    year: int
    month: int
    net_worth: Decimal
    total_assets: Decimal = Decimal("0")
    total_liabilities: Decimal = Decimal("0")

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
    def delta_30d(self) -> Decimal | None:
        """Net worth change vs ~30 days ago (approximated as one history step back).

        Returns None when history has fewer than 2 entries.
        """
        if len(self.history) < 2:
            return None
        return self.net_worth - self.history[-2].net_worth

    @property
    def delta_ytd(self) -> Decimal | None:
        """Net worth change since the start of the current year.

        Uses the first history entry in the current year as the baseline. Returns
        None when no entry from the current year exists (besides the current month).
        """
        today = datetime.date.today()
        # Find the earliest entry in the current year.
        for entry in self.history:
            if entry.year == today.year:
                if entry.year == today.year and entry.month == today.month:
                    # Only the current month's entry exists in-year — no baseline.
                    return None
                return self.net_worth - entry.net_worth
        return None

    @property
    def has_unknown_rates(self) -> bool:
        """True if any foreign-currency account has no known exchange rate."""
        return any(not a.rate_known and a.currency != self.default_currency for a in self.accounts)


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
        foreign_currencies = {a.currency for a in accounts_raw if a.currency != default_currency}

        # Load full rate history for batch lookups
        rate_history = await self._rate_svc.load_rates_for_currencies(
            foreign_currencies, default_currency
        )

        # Build current account snapshots using today's rate
        accounts = self._apply_rates(accounts_raw, rate_history, today, default_currency)

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
            rate: Decimal | None
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
        """Walk each account backwards month-by-month, classifying by kind.

        Gives us a per-month split of total_assets vs total_liabilities so the
        trend chart can stack them. Physical assets are treated as constant
        (we don't track their historical value for now).
        """
        today = datetime.date.today()
        physical_total = sum((a.value for a in physical_assets), Decimal("0"))

        # Per-account running balance in default currency — starts at current balance.
        balances: dict[int, Decimal] = {}
        kinds: dict[int, AccountType] = {}
        for a in accounts_raw:
            if a.currency == default_currency:
                rate = Decimal("1")
            else:
                rate = _nearest_rate(rate_history.get(a.currency, []), today) or Decimal("1")
            balances[a.id] = a.balance * rate
            kinds[a.id] = a.type

        # Per-account monthly signed delta from real transactions.
        #   INCOME  : +amount
        #   EXPENSE : -amount
        # Internal transfers are excluded — paired legs cancel at the aggregate
        # level, so for net-worth history (where we sum across all accounts) the
        # simpler exclusion keeps results correct without needing to pair legs.
        result = await self.session.execute(
            select(
                Transaction.account_id,
                func.strftime("%Y", Transaction.date).label("year"),
                func.strftime("%m", Transaction.date).label("month"),
                Transaction.type,
                func.sum(Transaction.amount).label("total"),
            )
            .where(
                Transaction.is_internal_transfer == False,  # noqa: E712
                Transaction.type.in_([TransactionType.INCOME, TransactionType.EXPENSE]),
            )
            .group_by(Transaction.account_id, "year", "month", Transaction.type)
        )

        per_account_delta: dict[tuple[int, int, int], Decimal] = {}
        for row in result:
            signed = row.total if row.type == TransactionType.INCOME else -row.total
            key = (row.account_id, int(row.year), int(row.month))
            per_account_delta[key] = per_account_delta.get(key, Decimal("0")) + signed

        snapshots: list[MonthlyNetWorth] = []
        for i in range(months):
            total = today.year * 12 + today.month - 1 - i
            y, m = total // 12, total % 12 + 1

            assets_total = physical_total
            liabilities_total = Decimal("0")
            for acc_id, bal in balances.items():
                if is_liability_kind(kinds[acc_id]):
                    liabilities_total += -bal  # liabilities display as positive
                else:
                    assets_total += bal

            net = assets_total - liabilities_total
            snapshots.insert(
                0,
                MonthlyNetWorth(
                    year=y,
                    month=m,
                    net_worth=net,
                    total_assets=assets_total,
                    total_liabilities=liabilities_total,
                ),
            )

            # Roll each account back by subtracting its delta for this month.
            for acc_id in balances:
                delta = per_account_delta.get((acc_id, y, m), Decimal("0"))
                balances[acc_id] -= delta

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
