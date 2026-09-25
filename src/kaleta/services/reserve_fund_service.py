# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import builtins
import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import ValidationError
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

#: The window in months, for turning its total into a monthly figure. Shared
#: so the burn and the income the what-if simulator compares it against
#: cannot end up measured over different numbers of months.
TRAILING_WINDOW_MONTHS = Decimal(3)

#: The window a spending-derived target averages over. Longer than the
#: coverage window on purpose: a target should not jump with one expensive
#: quarter, while "how long would this last" should track current burn.
TARGET_WINDOW_DAYS = 365
TARGET_WINDOW_MONTHS = Decimal(12)


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
            target_from_spending=payload.target_from_spending,
        )
        await self._snapshot_derived_target(fund)
        self.session.add(fund)
        await self.session.commit()
        await self.session.refresh(fund)
        return fund

    async def get(self, fund_id: int) -> ReserveFund | None:
        result = await self.session.execute(select(ReserveFund).where(ReserveFund.id == fund_id))
        return result.scalar_one_or_none()

    async def list(self, *, include_archived: bool = False) -> builtins.list[ReserveFund]:
        stmt = select(ReserveFund).order_by(ReserveFund.id)
        if not include_archived:
            stmt = stmt.where(ReserveFund.is_archived == False)  # noqa: E712
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update(self, fund_id: int, payload: ReserveFundUpdate) -> ReserveFund | None:
        fund = await self.get(fund_id)
        if fund is None:
            return None
        data = payload.model_dump(exclude_unset=True)
        from_spending = data.get("target_from_spending", fund.target_from_spending)
        multiplier = data.get("emergency_multiplier", fund.emergency_multiplier)
        if from_spending and multiplier is None:
            raise ValidationError(
                "emergency_multiplier is required when target_from_spending is set"
            )
        for key, value in data.items():
            setattr(fund, key, value)
        await self._snapshot_derived_target(fund)
        await self.session.commit()
        await self.session.refresh(fund)
        return fund

    async def archive(self, fund_id: int) -> ReserveFund | None:
        fund = await self.get(fund_id)
        if fund is None:
            return None
        fund.is_archived = True
        fund.archived_at = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
        await self.session.commit()
        await self.session.refresh(fund)
        return fund

    async def unarchive(self, fund_id: int) -> ReserveFund | None:
        fund = await self.get(fund_id)
        if fund is None:
            return None
        fund.is_archived = False
        fund.archived_at = None
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
        result = await self.session.execute(select(Account.balance).where(Account.id == account_id))
        bal = result.scalar_one_or_none()
        return bal if bal is not None else Decimal("0.00")

    async def trailing_monthly_expense(
        self,
        *,
        today: datetime.date | None = None,
        window_days: int = TRAILING_WINDOW_DAYS,
        window_months: Decimal = TRAILING_WINDOW_MONTHS,
    ) -> Decimal:
        """Average monthly expense over a trailing window (90 days by default).

        Public because the what-if simulator measures its runway against the
        same burn this panel does. Two copies of the formula would let the
        two screens disagree about how long the money lasts. The window is a
        parameter so the spending-derived target (12 months, see
        :meth:`derived_target`) reuses this formula rather than forking it.

        Only non-transfer expense transactions count. Returns Decimal("0")
        when there is no history.
        """
        ref = today or datetime.date.today()
        start = ref - datetime.timedelta(days=window_days)
        result = await self.session.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.type == TransactionType.EXPENSE,
                Transaction.is_internal_transfer == False,  # noqa: E712
                Transaction.date >= start,
                Transaction.date <= ref,
            )
        )
        total = result.scalar_one() or Decimal("0")
        return Decimal(total) / window_months

    async def target_monthly_expense(self, *, today: datetime.date | None = None) -> Decimal:
        """Average monthly expense over the 12-month window a derived target uses."""
        return await self.trailing_monthly_expense(
            today=today,
            window_days=TARGET_WINDOW_DAYS,
            window_months=TARGET_WINDOW_MONTHS,
        )

    async def derived_target(
        self, fund: ReserveFund, *, today: datetime.date | None = None
    ) -> Decimal | None:
        """Multiplier × average monthly expense over the last 12 months.

        ``None`` when the fund has no multiplier — there is nothing to
        multiply. Zero when there is no spending history in the window.
        """
        if fund.emergency_multiplier is None:
            return None
        monthly = await self.target_monthly_expense(today=today)
        return self.target_from_monthly(monthly, fund.emergency_multiplier)

    @staticmethod
    def target_from_monthly(monthly: Decimal, multiplier: int) -> Decimal:
        """Multiplier × monthly spend, to the grosz.

        Shared with the dialog's preview so the hint and the saved card
        cannot round differently.
        """
        return (monthly * Decimal(multiplier)).quantize(Decimal("0.01"))

    async def _effective_target(
        self, fund: ReserveFund, *, today: datetime.date | None = None
    ) -> Decimal:
        if fund.target_from_spending:
            derived = await self.derived_target(fund, today=today)
            if derived is not None:
                return derived
        return fund.target_amount

    async def _snapshot_derived_target(self, fund: ReserveFund) -> None:
        """Store today's derived target in ``target_amount``.

        Readers that take the column as-is (the wizard projection, the REST
        list) then see the figure as of the last save instead of a stale
        manual number the user switched away from.
        """
        if fund.target_from_spending:
            fund.target_amount = await self._effective_target(fund)

    async def with_progress(
        self, fund: ReserveFund, *, today: datetime.date | None = None
    ) -> ReserveFundWithProgress:
        balance = Decimal("0.00")
        if (
            fund.backing_mode == ReserveFundBackingMode.ACCOUNT
            and fund.backing_account_id is not None
        ):
            balance = await self._account_balance(fund.backing_account_id)

        target = await self._effective_target(fund, today=today)
        pct = (balance / target).quantize(Decimal("0.01")) if target > 0 else Decimal("0.00")

        months_of_coverage: Decimal | None = None
        if fund.kind == ReserveFundKind.EMERGENCY:
            monthly = await self.trailing_monthly_expense(today=today)
            if monthly > 0:
                months_of_coverage = (balance / monthly).quantize(Decimal("0.1"))

        return ReserveFundWithProgress.model_validate(
            {
                "id": fund.id,
                "name": fund.name,
                "kind": fund.kind,
                "target_amount": target,
                "backing_mode": fund.backing_mode,
                "backing_account_id": fund.backing_account_id,
                "backing_category_id": fund.backing_category_id,
                "emergency_multiplier": fund.emergency_multiplier,
                "target_from_spending": fund.target_from_spending,
                "is_archived": fund.is_archived,
                "archived_at": fund.archived_at,
                "current_balance": balance,
                "progress_pct": pct,
                "months_of_coverage": months_of_coverage,
            }
        )

    async def list_with_progress(
        self, *, today: datetime.date | None = None, include_archived: bool = False
    ) -> builtins.list[ReserveFundWithProgress]:
        funds = await self.list(include_archived=include_archived)
        return [await self.with_progress(f, today=today) for f in funds]

    @staticmethod
    def emergency_cover(funds: builtins.list[ReserveFundWithProgress]) -> Decimal | None:
        """Months the emergency funds cover between them, or ``None``.

        Every fund's cover is its balance over the *same* trailing monthly
        spend (see :meth:`with_progress`), so two emergency funds cover the
        sum of their months. Answering with the first would pick whichever id
        happened to be lower and leave the other fund out of a figure that
        means "how long could I live on this".

        ``None`` means there is no answer to give: no emergency fund, or no
        spending in the trailing window to measure one against. It is not
        the same as zero — a fund with nothing in it, on a ledger that has
        spending, covers ``0.0`` months and says so.
        """
        covers = [
            fund.months_of_coverage
            for fund in funds
            if fund.kind == ReserveFundKind.EMERGENCY and fund.months_of_coverage is not None
        ]
        return sum(covers, Decimal("0")) if covers else None

    async def emergency_progress(
        self, *, today: datetime.date | None = None
    ) -> builtins.list[ReserveFundWithProgress]:
        """The emergency funds, with their balances and cover.

        Only the emergency funds are costed: :meth:`with_progress` runs a
        balance query per fund and the trailing-spend aggregate per emergency
        one, and the cover figure is on the dashboard's first paint. A sinking
        fund cannot change that answer, so it is not worth a query.

        Callers that need the balances as well as the ratio — the what-if
        simulator does — take this rather than recovering a balance from a
        ratio already rounded to a tenth of a month.
        """
        funds = [f for f in await self.list() if f.kind == ReserveFundKind.EMERGENCY]
        return [await self.with_progress(f, today=today) for f in funds]

    async def emergency_cover_months(self, *, today: datetime.date | None = None) -> Decimal | None:
        """The dashboard's Safety-fund-cover figure. See :meth:`emergency_cover`."""
        return self.emergency_cover(await self.emergency_progress(today=today))


__all__ = [
    "TARGET_WINDOW_DAYS",
    "TARGET_WINDOW_MONTHS",
    "TRAILING_WINDOW_DAYS",
    "TRAILING_WINDOW_MONTHS",
    "ReserveFundService",
]
