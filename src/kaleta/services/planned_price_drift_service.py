# SPDX-License-Identifier: AGPL-3.0-or-later
"""Price drift — a planned charge that started costing something else.

A plan made from a detected recurring charge (KAL-REC-002) knows its payee.
When a new payment to that payee arrives at a price more than
``PRICE_DRIFT_TOLERANCE`` away from the plan, the plan is flagged and the user
is offered to update it (KAL-REC-004). Plans without a payee fall back to the
detector's merchant key of the plan's name.
"""

from __future__ import annotations

import datetime
import logging
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import NotFoundError, ValidationError
from kaleta.models.payee import Payee
from kaleta.models.planned_transaction import PlannedTransaction
from kaleta.models.transaction import Transaction, TransactionType
from kaleta.schemas.planned_transaction import PlannedPriceDrift
from kaleta.services.subscription_service import merchant_key_from_description

logger = logging.getLogger(__name__)

# Plan default: anything within ±5 % is rounding, FX or a promo — not a new price.
PRICE_DRIFT_TOLERANCE = Decimal("0.05")

_CENTS = Decimal("0.01")
_PCT = Decimal("0.1")


class PlannedPriceDriftService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def detect(self) -> list[PlannedPriceDrift]:
        """Active expense plans whose latest new payment drifted beyond tolerance.

        A payment matches a plan when it pays the plan's payee — or, for a
        payee-less plan, when its payee name or description reduces to the
        same merchant key as the plan's name. Only payments that are *new*
        count: dated no earlier than the day the plan was created, and not
        linked to any plan (a linked row is either a posted occurrence of a
        plan, written at the planned amount, or history a detection handed
        over). The latest such payment decides: once the plan is updated to
        the new price, the flag clears by itself.
        """
        plans_result = await self.session.execute(
            select(PlannedTransaction)
            .where(
                PlannedTransaction.is_active.is_(True),
                PlannedTransaction.type == TransactionType.EXPENSE,
            )
            .order_by(PlannedTransaction.name, PlannedTransaction.id)
        )
        plans = list(plans_result.scalars().all())
        if not plans:
            return []

        since = min(_created_on(p) for p in plans)
        tx_result = await self.session.execute(
            select(Transaction, Payee)
            .outerjoin(Payee, Transaction.payee_id == Payee.id)
            .where(
                Transaction.type == TransactionType.EXPENSE,
                Transaction.is_internal_transfer == False,  # noqa: E712
                Transaction.planned_transaction_id.is_(None),
                Transaction.date >= since,
            )
            .order_by(Transaction.date, Transaction.id)
        )
        # Ordered oldest → newest, so the last match per plan wins.
        payments = [(tx, _keys(tx, payee)) for tx, payee in tx_result.all()]

        drifts: list[PlannedPriceDrift] = []
        for plan in plans:
            created_on = _created_on(plan)
            plan_key = merchant_key_from_description(plan.name)
            latest: Transaction | None = None
            for tx, keys in payments:
                if tx.date < created_on:
                    continue
                if plan.payee_id is not None:
                    if tx.payee_id != plan.payee_id:
                        continue
                elif not plan_key or plan_key not in keys:
                    continue
                latest = tx
            if latest is None:
                continue
            drift = _drift(plan, latest)
            if drift is not None:
                drifts.append(drift)
        logger.debug("Price drift flagged on %s plan(s)", len(drifts))
        return drifts

    async def accept(self, planned_id: int, new_amount: Decimal) -> PlannedTransaction:
        """Update the plan to the new price the flag reported."""
        if new_amount <= 0:
            raise ValidationError("A planned transaction needs a positive amount")
        plan = await self.session.get(PlannedTransaction, planned_id)
        if plan is None:
            raise NotFoundError(f"Planned transaction {planned_id} not found")
        plan.amount = new_amount.quantize(_CENTS, rounding=ROUND_HALF_UP)
        await self.session.commit()
        logger.info("Planned transaction %s updated to new price %s", planned_id, plan.amount)
        return plan


def _created_on(plan: PlannedTransaction) -> datetime.date:
    return plan.created_at.date()


def _keys(tx: Transaction, payee: Payee | None) -> set[str]:
    """Merchant keys a payment answers to — its payee's name and its description."""
    keys = {merchant_key_from_description(tx.description)}
    if payee is not None:
        keys.add(merchant_key_from_description(payee.name))
    keys.discard("")
    return keys


def _drift(plan: PlannedTransaction, payment: Transaction) -> PlannedPriceDrift | None:
    planned = abs(plan.amount)
    paid = abs(payment.amount)
    if planned <= 0:
        return None
    change = (paid - planned) / planned
    if abs(change) <= PRICE_DRIFT_TOLERANCE:
        return None
    return PlannedPriceDrift(
        planned_id=plan.id,
        name=plan.name,
        planned_amount=planned,
        payment_amount=paid,
        payment_date=payment.date,
        change_pct=(change * 100).quantize(_PCT, rounding=ROUND_HALF_UP),
    )


__all__ = ["PRICE_DRIFT_TOLERANCE", "PlannedPriceDriftService"]
