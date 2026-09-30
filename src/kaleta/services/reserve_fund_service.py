# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import builtins
import datetime
from decimal import ROUND_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import NotFoundError, ValidationError
from kaleta.models.account import Account
from kaleta.models.reserve_fund import (
    ReserveFund,
    ReserveFundBackingMode,
    ReserveFundKind,
)
from kaleta.models.transaction import Transaction, TransactionType, TransferDirection
from kaleta.schemas.reserve_fund import (
    GoalClose,
    GoalContribution,
    ReserveFundCreate,
    ReserveFundUpdate,
    ReserveFundWithProgress,
)
from kaleta.schemas.transaction import TransactionCreate
from kaleta.services.account_service import AccountService
from kaleta.services.transaction_service import TransactionService

#: The kind a savings goal (skarbonka) is. Target date, contributions, pace
#: and close-with-release are goal features.
GOAL_KIND = ReserveFundKind.VACATION

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
            target_date=payload.target_date,
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
        if fund.kind != GOAL_KIND:
            # A fund edited out of being a goal leaves its date behind.
            fund.target_date = None
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
        return await AccountService(self.session).balance(account_id)

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

    # ── Savings goals ────────────────────────────────────────────────────────

    @staticmethod
    def months_left(today: datetime.date, target_date: datetime.date) -> int:
        """Whole months from *today* until *target_date*, never negative.

        2026-07-01 → 2027-06-01 is 11. A month only counts once its day has
        come round: 2026-07-15 → 2027-06-01 is 10.
        """
        months = (target_date.year - today.year) * 12 + target_date.month - today.month
        if target_date.day < today.day:
            months -= 1
        return max(months, 0)

    @staticmethod
    def monthly_pace(target: Decimal, saved: Decimal, months_left: int) -> Decimal:
        """What must go in each remaining month to reach *target*.

        Rounded up to the grosz, so paying the pace every month gets there.
        With no whole month left the whole remainder is due now; a goal
        already reached needs nothing more.
        """
        remaining = target - saved
        if remaining <= 0:
            return Decimal("0.00")
        return (remaining / Decimal(max(months_left, 1))).quantize(
            Decimal("0.01"), rounding=ROUND_UP
        )

    async def _goal(self, fund_id: int) -> tuple[ReserveFund, int]:
        """The active goal *fund_id* and its backing account id, or an error."""
        fund = await self.get(fund_id)
        if fund is None:
            raise NotFoundError(f"Reserve fund {fund_id} not found.")
        if fund.kind != GOAL_KIND:
            raise ValidationError("Only a savings goal takes contributions or closes.")
        if fund.is_archived:
            raise ValidationError("This goal is already closed.")
        if fund.backing_account_id is None:
            raise ValidationError("This goal has no backing account.")
        return fund, fund.backing_account_id

    async def _move(
        self,
        *,
        source_id: int,
        target_id: int,
        amount: Decimal,
        on: datetime.date,
        description: str,
    ) -> None:
        """One internal transfer between two of the user's accounts."""
        if source_id == target_id:
            raise ValidationError("Money cannot move from an account to itself.")
        result = await self.session.execute(
            select(Account.id, Account.currency).where(Account.id.in_([source_id, target_id]))
        )
        currencies: dict[int, str] = {account_id: currency for account_id, currency in result}
        for account_id in (source_id, target_id):
            if account_id not in currencies:
                raise NotFoundError(f"Account {account_id} not found.")
        if currencies[source_id] != currencies[target_id]:
            raise ValidationError("Both accounts must use the same currency.")

        def leg(account_id: int, direction: TransferDirection) -> TransactionCreate:
            return TransactionCreate(
                account_id=account_id,
                amount=amount,
                type=TransactionType.TRANSFER,
                transfer_direction=direction,
                date=on,
                description=description,
                is_internal_transfer=True,
            )

        await TransactionService(self.session).create_transfer(
            leg(source_id, TransferDirection.OUT), leg(target_id, TransferDirection.IN)
        )

    async def contribute(self, fund_id: int, payload: GoalContribution) -> None:
        """Put money into a goal: a transfer into its backing account.

        The goal's balance is that account's, which follows the ledger, so
        the card moves with no bookkeeping of its own.
        """
        _, backing_id = await self._goal(fund_id)
        await self._move(
            source_id=payload.from_account_id,
            target_id=backing_id,
            amount=payload.amount,
            on=payload.date,
            description=payload.description,
        )

    async def last_contribution_source(self, fund_id: int) -> int | None:
        """The account the goal's latest incoming transfer came from, if any.

        The close dialog offers it as where the money goes back to.
        """
        fund = await self.get(fund_id)
        if fund is None or fund.backing_account_id is None:
            return None
        incoming = (
            select(Transaction.linked_transaction_id)
            .where(
                Transaction.account_id == fund.backing_account_id,
                Transaction.transfer_direction == TransferDirection.IN,
                Transaction.linked_transaction_id.is_not(None),
            )
            .order_by(Transaction.date.desc(), Transaction.id.desc())
            .limit(1)
            .scalar_subquery()
        )
        result = await self.session.execute(
            select(Transaction.account_id).where(Transaction.id == incoming)
        )
        return result.scalar_one_or_none()

    async def close(self, fund_id: int, payload: GoalClose) -> ReserveFund:
        """Archive a goal, first moving its balance to *release_to_account_id*.

        No account means the money stays where it is. Nothing is moved when
        the backing account holds nothing.
        """
        _, backing_id = await self._goal(fund_id)
        if payload.release_to_account_id is not None:
            balance = await AccountService(self.session).balance(backing_id)
            if balance > 0:
                await self._move(
                    source_id=backing_id,
                    target_id=payload.release_to_account_id,
                    amount=balance,
                    on=payload.date,
                    description=payload.description,
                )
        archived = await self.archive(fund_id)
        if archived is None:  # deleted between the two steps
            raise NotFoundError(f"Reserve fund {fund_id} not found.")
        return archived

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
        months_left: int | None = None
        monthly_pace: Decimal | None = None
        if fund.kind == GOAL_KIND and fund.target_date is not None:
            months_left = self.months_left(today or datetime.date.today(), fund.target_date)
            monthly_pace = self.monthly_pace(target, balance, months_left)
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
                "target_date": fund.target_date,
                "months_left": months_left,
                "monthly_pace": monthly_pace,
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
    "GOAL_KIND",
    "TARGET_WINDOW_DAYS",
    "TARGET_WINDOW_MONTHS",
    "TRAILING_WINDOW_DAYS",
    "TRAILING_WINDOW_MONTHS",
    "ReserveFundService",
]
