# SPDX-License-Identifier: AGPL-3.0-or-later
"""The annual review: close a year and set up the next (``budgets-annual-review``, ``KAL-ANR``).

Three steps over services that already exist. The year's plan against its
spending (the budget grid's figures); the carry of the year's yearly plan into
the next, category by category with a % adjustment, through
``YearlyPlanService``'s diff and apply; and the commitments — subscriptions and
irregular-fund items — each kept, adjusted or dropped.
"""

from __future__ import annotations

import builtins
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import NotFoundError, ValidationError
from kaleta.models.reserve_fund import ReserveFundKind
from kaleta.models.subscription import SubscriptionStatus
from kaleta.schemas.annual_review import (
    AnnualCarry,
    AnnualCategoryYear,
    AnnualSummary,
    CarryCategory,
    Commitment,
    CommitmentKind,
)
from kaleta.schemas.category import CategoryType
from kaleta.schemas.irregular_item import IrregularItemUpdate
from kaleta.schemas.subscription import SubscriptionUpdate
from kaleta.schemas.yearly_plan import FixedLine, VariableLine, YearlyPlanPayload
from kaleta.services.budget_service import BudgetService
from kaleta.services.category_service import CategoryService
from kaleta.services.irregular_item_service import IrregularItemService
from kaleta.services.reserve_fund_service import ReserveFundService
from kaleta.services.subscription_service import SubscriptionService
from kaleta.services.text_order import text_key
from kaleta.services.yearly_plan_service import YearlyPlanService

_CENTS = Decimal("0.01")
_DAYS_IN_YEAR = Decimal(365)


def _cents(value: Decimal) -> Decimal:
    return value.quantize(_CENTS, rounding=ROUND_HALF_UP)


def adjusted(amount: Decimal, pct: Decimal) -> Decimal:
    """``amount`` raised (or lowered) by ``pct`` per cent, to the grosz."""
    return _cents(amount * (Decimal(100) + pct) / Decimal(100))


class AnnualReviewService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _expense_names(self) -> dict[int, str]:
        categories = await CategoryService(self.session).list()
        return {c.id: c.name for c in categories if c.type == CategoryType.EXPENSE}

    async def _planned(self, year: int) -> dict[int, Decimal]:
        totals: dict[int, Decimal] = defaultdict(lambda: Decimal("0.00"))
        for budget in await BudgetService(self.session).list_for_year(year):
            totals[budget.category_id] += budget.amount
        return dict(totals)

    # ── Step 1 (``KAL-ANR-001``) ──────────────────────────────────────────

    async def summary(self, year: int) -> AnnualSummary:
        names = await self._expense_names()
        planned = await self._planned(year)
        actual: dict[int, Decimal] = defaultdict(lambda: Decimal("0.00"))
        for (category_id, _month), amount in (
            await BudgetService(self.session).actuals_by_category_month(year)
        ).items():
            actual[category_id] += amount
        rows = [
            AnnualCategoryYear(
                category_id=cid,
                name=names[cid],
                planned=planned.get(cid, Decimal("0.00")),
                actual=_cents(actual.get(cid, Decimal("0.00"))),
            )
            for cid in set(planned) | set(actual)
            if cid in names
        ]
        rows.sort(key=lambda r: text_key(r.name))
        return AnnualSummary(
            year=year,
            rows=rows,
            planned_total=sum((r.planned for r in rows), Decimal("0.00")),
            actual_total=sum((r.actual for r in rows), Decimal("0.00")),
        )

    # ── Step 2 (``KAL-ANR-002``) ──────────────────────────────────────────

    async def carry(self, year: int, adjustments: dict[int, Decimal] | None = None) -> AnnualCarry:
        """Next year's yearly plan: this year's, each category moved by its %.

        Income and reserve lines go over as they are. A fixed or variable line
        moves by its category's %. Budgets set by hand on the grid — more for a
        category than this year's lines derive — become a variable line of
        their own, moved the same way.
        """
        pct = adjustments or {}
        if any(p < Decimal("-100") for p in pct.values()):
            raise ValidationError("A category cannot go down by more than 100%.")
        plans = YearlyPlanService(self.session)
        this = await plans.get_payload(year)
        names = await self._expense_names()
        planned = await self._planned(year)
        derived: dict[int, Decimal] = defaultdict(lambda: Decimal("0.00"))
        for (category_id, _month), amount in plans.derive(this).items():
            derived[category_id] += amount

        def _move(amount: Decimal, category_id: int | None) -> Decimal:
            if category_id is None:
                return amount
            return adjusted(amount, pct.get(category_id, Decimal("0")))

        fixed = [
            FixedLine(name=f.name, amount=_move(f.amount, f.category_id), category_id=f.category_id)
            for f in this.fixed_lines
        ]
        variable = [
            VariableLine(
                name=v.name, amount=_move(v.amount, v.category_id), category_id=v.category_id
            )
            for v in this.variable_lines
        ]
        for category_id in sorted(planned, key=lambda c: text_key(names.get(c, ""))):
            rest = planned[category_id] - derived.get(category_id, Decimal("0.00"))
            if rest > 0 and category_id in names:
                variable.append(
                    VariableLine(
                        name=names[category_id][:100],
                        amount=_move(rest, category_id),
                        category_id=category_id,
                    )
                )
        payload = YearlyPlanPayload(
            year=year + 1,
            income_lines=list(this.income_lines),
            fixed_lines=fixed,
            variable_lines=variable,
            reserves_lines=list(this.reserves_lines),
        )

        next_totals: dict[int, Decimal] = defaultdict(lambda: Decimal("0.00"))
        for (category_id, _month), amount in plans.derive(payload).items():
            next_totals[category_id] += amount
        carried = (set(planned) | set(derived)) & set(names)
        rows = sorted(
            (
                CarryCategory(
                    category_id=cid,
                    name=names[cid],
                    planned=max(
                        planned.get(cid, Decimal("0.00")), derived.get(cid, Decimal("0.00"))
                    ),
                    pct=pct.get(cid, Decimal("0")),
                    next_amount=next_totals.get(cid, Decimal("0.00")),
                )
                for cid in carried
            ),
            key=lambda r: text_key(r.name),
        )
        return AnnualCarry(
            year=year,
            rows=rows,
            payload=payload,
            replaces_plan=await plans.get(year + 1) is not None,
        )

    # ── Step 3 (``KAL-ANR-003``) ──────────────────────────────────────────

    async def commitments(self) -> builtins.list[Commitment]:
        """Every active subscription, then every item of every irregular fund."""
        rows: builtins.list[Commitment] = []
        for sub in await SubscriptionService(self.session).list(status=SubscriptionStatus.ACTIVE):
            if sub.cancelled_at is not None:
                continue  # already on its way out
            rows.append(
                Commitment(
                    kind=CommitmentKind.SUBSCRIPTION,
                    id=sub.id,
                    name=sub.name,
                    amount=sub.amount,
                    yearly=_cents(sub.amount * _DAYS_IN_YEAR / Decimal(max(sub.cadence_days, 1))),
                )
            )
        items = IrregularItemService(self.session)
        for fund in await ReserveFundService(self.session).list():
            if fund.kind is not ReserveFundKind.IRREGULAR:
                continue
            rows.extend(
                Commitment(
                    kind=CommitmentKind.IRREGULAR_ITEM,
                    id=item.id,
                    name=item.name,
                    amount=item.yearly_amount,
                    yearly=item.yearly_amount,
                )
                for item in await items.items(fund.id)
            )
        return rows

    async def adjust(self, kind: CommitmentKind, commitment_id: int, amount: Decimal) -> None:
        """A subscription's new charge, or an item's new yearly amount."""
        if kind is CommitmentKind.SUBSCRIPTION:
            updated = await SubscriptionService(self.session).update(
                commitment_id, SubscriptionUpdate(amount=amount)
            )
            if updated is None:
                raise NotFoundError(f"Subscription {commitment_id} not found.")
        else:
            await IrregularItemService(self.session).update(
                commitment_id, IrregularItemUpdate(yearly_amount=amount)
            )

    async def drop(self, kind: CommitmentKind, commitment_id: int) -> None:
        """Cancel the subscription today, or delete the item."""
        if kind is CommitmentKind.SUBSCRIPTION:
            if await SubscriptionService(self.session).cancel(commitment_id) is None:
                raise NotFoundError(f"Subscription {commitment_id} not found.")
        else:
            await IrregularItemService(self.session).delete(commitment_id)
