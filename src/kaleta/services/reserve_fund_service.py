from __future__ import annotations

import builtins
import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.account import Account
from kaleta.models.reserve_fund import (
    ReserveFund,
    ReserveFundBackingMode,
    ReserveFundKind,
)
from kaleta.models.transaction import Transaction, TransactionType
from kaleta.schemas.reserve_fund import (
    ReserveFundCreate,
    ReserveFundUpdate,
    ReserveFundWithProgress,
)

TRAILING_WINDOW_DAYS = 90


class ReserveFundService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, payload: ReserveFundCreate) -> ReserveFund:
        fund = ReserveFund(
            name=payload.name,
            kind=payload.kind,
            target_amount=payload.target_amount,
            backing_mode=payload.backing_mode,
            backing_account_id=payload.backing_account_id,
            backing_category_id=payload.backing_category_id,
            emergency_multiplier=payload.emergency_multiplier,
        )
        self.session.add(fund)
        await self.session.commit()
        await self.session.refresh(fund)
        return fund

    async def get(self, fund_id: int) -> ReserveFund | None:
        result = await self.session.execute(
            select(ReserveFund).where(ReserveFund.id == fund_id)
        )
        return result.scalar_one_or_none()

    async def list(self) -> builtins.list[ReserveFund]:
        result = await self.session.execute(
            select(ReserveFund).order_by(ReserveFund.id)
        )
        return list(result.scalars().all())

    async def update(self, fund_id: int, payload: ReserveFundUpdate) -> ReserveFund | None:
        fund = await self.get(fund_id)
        if fund is None:
            return None
        data = payload.model_dump(exclude_unset=True)
        for key, value in data.items():
            setattr(fund, key, value)
        await self.session.commit()
        await self.session.refresh(fund)
        return fund

    async def delete(self, fund_id: int) -> bool:
        fund = await self.get(fund_id)
        if fund is None:
            return False
        await self.session.delete(fund)
        await self.session.commit()
        return True

    async def _account_balance(self, account_id: int) -> Decimal:
        result = await self.session.execute(
            select(Account.balance).where(Account.id == account_id)
        )
        bal = result.scalar_one_or_none()
        return bal if bal is not None else Decimal("0.00")

    async def _trailing_monthly_expense(
        self, *, today: datetime.date | None = None
    ) -> Decimal:
        """Average monthly expense over the trailing 90-day window.

        Only non-transfer expense transactions count. Returns Decimal("0")
        when there is no history.
        """
        ref = today or datetime.date.today()
        start = ref - datetime.timedelta(days=TRAILING_WINDOW_DAYS)
        result = await self.session.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.type == TransactionType.EXPENSE,
                Transaction.is_internal_transfer == False,  # noqa: E712
                Transaction.date >= start,
                Transaction.date <= ref,
            )
        )
        total = result.scalar_one() or Decimal("0")
        # 90 days ≈ 3 months → divide by 3 to land on a monthly figure.
        return Decimal(total) / Decimal(3)

    async def with_progress(
        self, fund: ReserveFund, *, today: datetime.date | None = None
    ) -> ReserveFundWithProgress:
        balance = Decimal("0.00")
        if (
            fund.backing_mode == ReserveFundBackingMode.ACCOUNT
            and fund.backing_account_id is not None
        ):
            balance = await self._account_balance(fund.backing_account_id)

        if fund.target_amount > 0:
            pct = (balance / fund.target_amount).quantize(Decimal("0.01"))
        else:
            pct = Decimal("0.00")

        months_of_coverage: Decimal | None = None
        if fund.kind == ReserveFundKind.EMERGENCY:
            monthly = await self._trailing_monthly_expense(today=today)
            if monthly > 0:
                months_of_coverage = (balance / monthly).quantize(Decimal("0.1"))

        return ReserveFundWithProgress.model_validate(
            {
                "id": fund.id,
                "name": fund.name,
                "kind": fund.kind,
                "target_amount": fund.target_amount,
                "backing_mode": fund.backing_mode,
                "backing_account_id": fund.backing_account_id,
                "backing_category_id": fund.backing_category_id,
                "emergency_multiplier": fund.emergency_multiplier,
                "current_balance": balance,
                "progress_pct": pct,
                "months_of_coverage": months_of_coverage,
            }
        )

    async def list_with_progress(
        self, *, today: datetime.date | None = None
    ) -> builtins.list[ReserveFundWithProgress]:
        funds = await self.list()
        return [await self.with_progress(f, today=today) for f in funds]


__all__ = ["ReserveFundService", "TRAILING_WINDOW_DAYS"]
