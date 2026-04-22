from __future__ import annotations

import json
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.category import Category
from kaleta.models.yearly_plan import YearlyPlan
from kaleta.schemas.budget import BudgetCreate
from kaleta.schemas.yearly_plan import (
    BudgetDiff,
    BudgetDiffEntry,
    FixedLine,
    IncomeLine,
    ReserveLine,
    VariableLine,
    YearlyPlanPayload,
)
from kaleta.services.budget_service import BudgetService

_TWO = Decimal("0.01")


def _split_yearly_to_months(amount: Decimal) -> list[Decimal]:
    """Split a yearly amount into 12 monthly values.

    Base month value is `amount / 12` rounded to 2 decimals. Any rounding
    remainder is spread across the last three months so the 12 values
    sum exactly to the yearly amount (per the plan's rounding rule).
    """
    if amount <= 0:
        return [Decimal("0.00")] * 12
    base = (amount / Decimal(12)).quantize(_TWO, rounding=ROUND_HALF_UP)
    monthly = [base] * 12
    remainder = (amount - base * 12).quantize(_TWO, rounding=ROUND_HALF_UP)
    if remainder == 0:
        return monthly
    # Distribute remainder evenly over the last 3 months (months 10, 11, 12)
    # in 0.01 cents. Positive and negative remainders both work.
    cents = int((remainder / _TWO).to_integral_value())
    idx = [11, 10, 9]
    step = 1 if cents > 0 else -1
    for i in range(abs(cents)):
        monthly[idx[i % 3]] += _TWO * step
    return monthly


class YearlyPlanService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, year: int) -> YearlyPlan | None:
        result = await self.session.execute(
            select(YearlyPlan).where(YearlyPlan.year == year)
        )
        return result.scalar_one_or_none()

    async def get_payload(self, year: int) -> YearlyPlanPayload:
        """Return the plan as an editable payload (empty payload if no row)."""
        plan = await self.get(year)
        if plan is None:
            return YearlyPlanPayload(year=year)
        return YearlyPlanPayload(
            year=plan.year,
            income_lines=[IncomeLine(**x) for x in json.loads(plan.income_lines)],
            fixed_lines=[FixedLine(**x) for x in json.loads(plan.fixed_lines)],
            variable_lines=[VariableLine(**x) for x in json.loads(plan.variable_lines)],
            reserves_lines=[ReserveLine(**x) for x in json.loads(plan.reserves_lines)],
        )

    async def upsert(self, payload: YearlyPlanPayload) -> YearlyPlan:
        existing = await self.get(payload.year)
        income_json = json.dumps([_line_dict(x) for x in payload.income_lines])
        fixed_json = json.dumps([_line_dict(x) for x in payload.fixed_lines])
        variable_json = json.dumps([_line_dict(x) for x in payload.variable_lines])
        reserves_json = json.dumps([_line_dict(x) for x in payload.reserves_lines])
        if existing:
            existing.income_lines = income_json
            existing.fixed_lines = fixed_json
            existing.variable_lines = variable_json
            existing.reserves_lines = reserves_json
            await self.session.commit()
            await self.session.refresh(existing)
            return existing
        plan = YearlyPlan(
            year=payload.year,
            income_lines=income_json,
            fixed_lines=fixed_json,
            variable_lines=variable_json,
            reserves_lines=reserves_json,
        )
        self.session.add(plan)
        await self.session.commit()
        await self.session.refresh(plan)
        return plan

    def derive(self, payload: YearlyPlanPayload) -> dict[tuple[int, int], Decimal]:
        """Return {(category_id, month): amount} from a payload.

        Only lines with a category_id contribute. Multiple lines targeting
        the same category are summed. Months are 1-indexed.
        """
        result: dict[tuple[int, int], Decimal] = {}

        def _add(cat_id: int, amount: Decimal) -> None:
            for i, v in enumerate(_split_yearly_to_months(amount)):
                if v == 0:
                    continue
                key = (cat_id, i + 1)
                result[key] = result.get(key, Decimal("0.00")) + v

        for fx in payload.fixed_lines:
            if fx.category_id is not None:
                _add(fx.category_id, fx.amount)
        for va in payload.variable_lines:
            _add(va.category_id, va.amount)

        return result

    async def diff(self, payload: YearlyPlanPayload) -> BudgetDiff:
        """Compare the derivation against current Budget rows for the year."""
        derived = self.derive(payload)
        cat_ids = {cid for (cid, _m) in derived}
        name_map: dict[int, str] = {}
        if cat_ids:
            rows = await self.session.execute(
                select(Category.id, Category.name).where(Category.id.in_(cat_ids))
            )
            name_map = {r.id: r.name for r in rows}

        current = await BudgetService(self.session).list_for_year(payload.year)
        current_map: dict[tuple[int, int], Decimal] = {
            (b.category_id, b.month): b.amount for b in current
        }

        added: list[BudgetDiffEntry] = []
        updated: list[BudgetDiffEntry] = []
        unchanged = 0
        for (cid, month), proposed in derived.items():
            cur = current_map.get((cid, month))
            entry = BudgetDiffEntry(
                category_id=cid,
                category_name=name_map.get(cid, f"#{cid}"),
                month=month,
                current=cur,
                proposed=proposed,
            )
            if cur is None:
                added.append(entry)
            elif cur != proposed:
                updated.append(entry)
            else:
                unchanged += 1

        return BudgetDiff(added=added, updated=updated, unchanged_count=unchanged)

    async def apply(self, payload: YearlyPlanPayload) -> int:
        """Upsert Budget rows for the year from the derivation. Returns row count."""
        await self.upsert(payload)
        derived = self.derive(payload)
        if not derived:
            return 0
        entries = [
            BudgetCreate(category_id=cid, amount=amt, month=month, year=payload.year)
            for (cid, month), amt in derived.items()
        ]
        return await BudgetService(self.session).bulk_upsert(entries)


def _line_dict(line: IncomeLine | FixedLine | VariableLine | ReserveLine) -> dict[str, object]:
    """Serialise a line to a JSON-friendly dict (Decimal → str for round-trip)."""
    d = line.model_dump()
    for k, v in list(d.items()):
        if isinstance(v, Decimal):
            d[k] = str(v)
    return d


__all__ = ["YearlyPlanService", "_split_yearly_to_months"]
