"""Prophet-based cashflow and balance forecasting service."""

from __future__ import annotations

import asyncio
import datetime
import logging
from dataclasses import dataclass, field
from functools import partial
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.account import Account
from kaleta.models.transaction import Transaction, TransactionType

if TYPE_CHECKING:
    from kaleta.services.planned_transaction_service import PlannedOccurrence

# Suppress noisy Stan / Prophet output
logging.getLogger("prophet").setLevel(logging.WARNING)
logging.getLogger("cmdstanpy").setLevel(logging.WARNING)


@dataclass
class ForecastPoint:
    date: datetime.date
    value: float
    lower: float
    upper: float
    is_forecast: bool


@dataclass
class ForecastResult:
    account_name: str
    points: list[ForecastPoint]
    insufficient_data: bool = False
    planned_occurrences: list[PlannedOccurrence] = field(default_factory=list)

    @property
    def historical(self) -> list[ForecastPoint]:
        return [p for p in self.points if not p.is_forecast]

    @property
    def forecast(self) -> list[ForecastPoint]:
        return [p for p in self.points if p.is_forecast]

    @property
    def predicted_balance_30d(self) -> float | None:
        target = datetime.date.today() + datetime.timedelta(days=30)
        candidates = [p for p in self.forecast if p.date >= target]
        return candidates[0].value if candidates else None


class ForecastService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def available_accounts(self) -> list[Account]:
        result = await self.session.execute(select(Account).order_by(Account.name))
        return list(result.scalars().all())

    async def forecast_account(
        self,
        account_id: int | None,
        horizon_days: int = 60,
        history_days: int = 365,
    ) -> ForecastResult:
        """Forecast daily balance for one account (or total if account_id is None)."""
        account_name = "All Accounts"
        if account_id is not None:
            account = await self.session.get(Account, account_id)
            account_name = account.name if account else f"Account {account_id}"

        # ── Pull daily net cashflow from DB ──────────────────────────────────
        since = datetime.date.today() - datetime.timedelta(days=history_days)

        stmt = (
            select(
                Transaction.date.label("day"),
                Transaction.type,
                func.sum(Transaction.amount).label("total"),
            )
            .where(
                Transaction.date >= since,
                Transaction.is_internal_transfer == False,  # noqa: E712
            )
            .group_by("day", Transaction.type)
            .order_by("day")
        )
        if account_id is not None:
            stmt = stmt.where(Transaction.account_id == account_id)

        result = await self.session.execute(stmt)
        rows = result.all()

        if not rows:
            return ForecastResult(account_name=account_name, points=[], insufficient_data=True)

        # Build daily net: income positive, expense negative
        daily: dict[datetime.date, float] = {}
        for row in rows:
            d = (
                row.day
                if isinstance(row.day, datetime.date)
                else datetime.date.fromisoformat(str(row.day))
            )
            if row.type == TransactionType.INCOME:
                daily[d] = daily.get(d, 0.0) + float(row.total)
            elif row.type == TransactionType.EXPENSE:
                daily[d] = daily.get(d, 0.0) - float(row.total)

        if len(daily) < 14:
            return ForecastResult(account_name=account_name, points=[], insufficient_data=True)

        # Get current balance as starting point
        if account_id is not None:
            account_obj = await self.session.get(Account, account_id)
            current_balance = float(account_obj.balance) if account_obj else 0.0
        else:
            total = await self.session.execute(select(func.sum(Account.balance)))
            val = total.scalar()
            current_balance = float(val) if val else 0.0

        # Build cumulative balance series (working backwards from current balance)
        sorted_days = sorted(daily.keys())
        # Running sum from oldest to newest, anchored at current_balance at last day
        cumulative_from_start = 0.0
        running: dict[datetime.date, float] = {}
        for d in sorted_days:
            cumulative_from_start += daily[d]
            running[d] = cumulative_from_start

        # Shift so that last day = current_balance
        offset = current_balance - running[sorted_days[-1]]
        for d in sorted_days:
            running[d] += offset

        # ── Run Prophet in thread pool ────────────────────────────────────────
        prophet_result = await asyncio.get_event_loop().run_in_executor(
            None,
            partial(_run_prophet, running, horizon_days),
        )

        if prophet_result is None:
            return ForecastResult(account_name=account_name, points=[], insufficient_data=True)

        history_dates = set(sorted_days)
        points = [
            ForecastPoint(
                date=row_date,
                value=round(yhat, 2),
                lower=round(lower, 2),
                upper=round(upper, 2),
                is_forecast=row_date not in history_dates,
            )
            for row_date, yhat, lower, upper in prophet_result
        ]

        # ── Overlay planned transactions on the forecast ──────────────────────
        from kaleta.services.planned_transaction_service import PlannedTransactionService

        today = datetime.date.today()
        horizon_end = today + datetime.timedelta(days=horizon_days)
        planned_svc = PlannedTransactionService(self.session)
        planned_occs = await planned_svc.get_occurrences(
            today + datetime.timedelta(days=1), horizon_end, account_id
        )

        if planned_occs:
            # Build daily delta map from planned transactions
            delta_by_date: dict[datetime.date, float] = {}
            for occ in planned_occs:
                amt = float(occ.amount)
                delta = amt if occ.type == TransactionType.INCOME else -amt
                delta_by_date[occ.date] = delta_by_date.get(occ.date, 0.0) + delta

            # Apply cumulative adjustment to forecast points (in chronological order)
            cumulative = 0.0
            for point in points:
                if point.is_forecast:
                    cumulative += delta_by_date.get(point.date, 0.0)
                    point.value = round(point.value + cumulative, 2)
                    point.lower = round(point.lower + cumulative, 2)
                    point.upper = round(point.upper + cumulative, 2)

        return ForecastResult(
            account_name=account_name,
            points=points,
            planned_occurrences=planned_occs,
        )


def _run_prophet(
    running: dict[datetime.date, float],
    horizon_days: int,
) -> list[tuple[datetime.date, float, float, float]] | None:
    """Synchronous Prophet fit + predict (runs in thread pool)."""
    try:
        import pandas as pd  # type: ignore[import-untyped]
        from prophet import Prophet  # type: ignore[import-untyped]

        df = pd.DataFrame([{"ds": d, "y": v} for d, v in sorted(running.items())])

        model = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=True,
            daily_seasonality=False,
            interval_width=0.80,
        )
        model.fit(df)

        future = model.make_future_dataframe(periods=horizon_days, freq="D")
        forecast = model.predict(future)

        return [
            (
                row["ds"].date(),
                row["yhat"],
                row["yhat_lower"],
                row["yhat_upper"],
            )
            for _, row in forecast.iterrows()
        ]
    except Exception:
        return None
