from __future__ import annotations

import calendar
import datetime
import json
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.category import Category
from kaleta.models.monthly_readiness import MonthlyReadiness
from kaleta.models.transaction import Transaction, TransactionType
from kaleta.schemas.monthly_readiness import (
    Stage1CloseLastMonth,
    Stage2ConfirmIncome,
    Stage2IncomeRow,
    Stage3AllocateNewMonth,
    Stage3CopyPreviewRow,
    Stage4AcknowledgeBills,
    Stage4PlannedRow,
)
from kaleta.services.budget_service import BudgetService
from kaleta.services.planned_transaction_service import PlannedTransactionService


def _prev_month(year: int, month: int) -> tuple[int, int]:
    if month == 1:
        return year - 1, 12
    return year, month - 1


def _month_bounds(year: int, month: int) -> tuple[datetime.date, datetime.date]:
    last_day = calendar.monthrange(year, month)[1]
    return datetime.date(year, month, 1), datetime.date(year, month, last_day)


class MonthlyReadinessService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Persistence ───────────────────────────────────────────────────────────

    async def get_or_create(self, year: int, month: int) -> MonthlyReadiness:
        result = await self.session.execute(
            select(MonthlyReadiness).where(
                MonthlyReadiness.year == year, MonthlyReadiness.month == month
            )
        )
        row = result.scalar_one_or_none()
        if row is not None:
            return row
        row = MonthlyReadiness(year=year, month=month)
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def mark_stage(
        self, year: int, month: int, stage: int, *, done: bool = True
    ) -> MonthlyReadiness:
        if stage not in (1, 2, 3, 4):
            raise ValueError(f"stage must be 1..4, got {stage}")
        row = await self.get_or_create(year, month)
        setattr(row, f"stage_{stage}_done", done)
        if row.stage_1_done and row.stage_2_done and row.stage_3_done and row.stage_4_done:
            if row.ready_at is None:
                row.ready_at = datetime.datetime.now(datetime.UTC)
        else:
            row.ready_at = None
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def set_seen(
        self, year: int, month: int, planned_id: int, *, seen: bool
    ) -> list[int]:
        row = await self.get_or_create(year, month)
        ids = set(json.loads(row.seen_planned_ids))
        if seen:
            ids.add(planned_id)
        else:
            ids.discard(planned_id)
        row.seen_planned_ids = json.dumps(sorted(ids))
        await self.session.commit()
        return sorted(ids)

    # ── Stage evaluators ──────────────────────────────────────────────────────

    async def stage_1(self, year: int, month: int) -> Stage1CloseLastMonth:
        last_year, last_month = _prev_month(year, month)
        start, end = _month_bounds(last_year, last_month)
        stmt = select(func.count(Transaction.id)).where(
            Transaction.date >= start,
            Transaction.date <= end,
            Transaction.category_id.is_(None),
            Transaction.type != TransactionType.TRANSFER,
        )
        count = (await self.session.execute(stmt)).scalar_one()
        return Stage1CloseLastMonth(
            last_year=last_year,
            last_month=last_month,
            uncategorised_count=int(count or 0),
        )

    async def stage_2(self, year: int, month: int) -> Stage2ConfirmIncome:
        start, end = _month_bounds(year, month)
        pts_svc = PlannedTransactionService(self.session)
        occurrences = await pts_svc.get_occurrences(start, end)
        # Per planned_id: sum expected income occurrences in the window.
        expected_by_pid: dict[int, tuple[str, Decimal]] = {}
        for o in occurrences:
            if o.type != TransactionType.INCOME:
                continue
            prev = expected_by_pid.get(o.planned_id)
            running_total = (prev[1] if prev else Decimal("0")) + o.amount
            expected_by_pid[o.planned_id] = (o.name, running_total)

        if not expected_by_pid:
            return Stage2ConfirmIncome(rows=[])

        # Actual income: sum Transactions of type=INCOME in window, grouped
        # by planned-transaction link (description match as a naive fallback).
        actual_stmt = select(
            func.coalesce(func.sum(Transaction.amount), 0)
        ).where(
            Transaction.type == TransactionType.INCOME,
            Transaction.date >= start,
            Transaction.date <= end,
            Transaction.is_internal_transfer == False,  # noqa: E712
        )
        actual_total = (await self.session.execute(actual_stmt)).scalar_one() or Decimal(
            "0"
        )
        # Distribute actual total proportionally by expected share — simple
        # v1 approximation; a future pass will match by description or a
        # dedicated foreign key.
        expected_sum = sum((v[1] for v in expected_by_pid.values()), Decimal("0"))
        rows: list[Stage2IncomeRow] = []
        for pid, (name, exp) in expected_by_pid.items():
            share = (exp / expected_sum) if expected_sum > 0 else Decimal("0")
            actual_share = (Decimal(actual_total) * share).quantize(Decimal("0.01"))
            rows.append(
                Stage2IncomeRow(planned_id=pid, name=name, expected=exp, actual=actual_share)
            )
        return Stage2ConfirmIncome(rows=rows)

    async def stage_3(self, year: int, month: int) -> Stage3AllocateNewMonth:
        from_year, from_month = _prev_month(year, month)
        bsvc = BudgetService(self.session)
        prev_rows = await bsvc.list_for_month(from_year, from_month)
        cur_rows = await bsvc.list_for_month(year, month)
        cur_ids = {b.category_id for b in cur_rows}

        cat_names: dict[int, str] = {}
        missing = [b.category_id for b in prev_rows if b.category_id not in cat_names]
        if missing:
            cats_res = await self.session.execute(
                select(Category.id, Category.name).where(Category.id.in_(missing))
            )
            cat_names = {r.id: r.name for r in cats_res}

        rows = [
            Stage3CopyPreviewRow(
                category_id=b.category_id,
                category_name=cat_names.get(b.category_id, f"#{b.category_id}"),
                amount=b.amount,
                already_set=b.category_id in cur_ids,
            )
            for b in prev_rows
        ]
        return Stage3AllocateNewMonth(
            from_year=from_year,
            from_month=from_month,
            to_year=year,
            to_month=month,
            rows=rows,
        )

    async def apply_stage_3(self, year: int, month: int) -> int:
        """Execute the copy-forward action for stage 3. Returns rows written."""
        from_year, from_month = _prev_month(year, month)
        bsvc = BudgetService(self.session)
        return await bsvc.copy_forward(from_year, from_month, year, month)

    async def stage_4(self, year: int, month: int) -> Stage4AcknowledgeBills:
        start, end = _month_bounds(year, month)
        pts_svc = PlannedTransactionService(self.session)
        occurrences = await pts_svc.get_occurrences(start, end)

        row = await self.get_or_create(year, month)
        seen_ids = set(json.loads(row.seen_planned_ids))

        rows = [
            Stage4PlannedRow(
                planned_id=o.planned_id,
                date=o.date,
                name=o.name,
                amount=o.amount,
                account_name=o.account_name,
                category_name=o.category_name,
                seen=o.planned_id in seen_ids,
            )
            for o in occurrences
            if o.type != TransactionType.INCOME
        ]
        return Stage4AcknowledgeBills(rows=rows)


__all__ = ["MonthlyReadinessService"]
