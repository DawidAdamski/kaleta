# SPDX-License-Identifier: AGPL-3.0-or-later
"""The irregular-expenses fund's plan: its yearly items and the monthly transfer that feeds it.

``funds-irregular-items`` (``KAL-IRR``). The fund itself is a ``ReserveFund``
of kind ``IRREGULAR``; this service owns what makes it a plan — the costs it
saves for, each set aside at a tenth a month (``kaleta.core.irregular``), and
the funding proposal that turns their sum into a monthly planned transfer
into the fund's account, the way the salary proposal does (``KAL-SAL-004``).
"""

from __future__ import annotations

import builtins
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.core.irregular import monthly_contribution
from kaleta.exceptions import ConflictError, NotFoundError, ValidationError
from kaleta.models.account import Account
from kaleta.models.irregular_item import IrregularItem
from kaleta.models.planned_transaction import PlannedTransaction, RecurrenceFrequency
from kaleta.models.reserve_fund import ReserveFund, ReserveFundKind
from kaleta.models.transaction import Transaction, TransactionType, TransferDirection
from kaleta.schemas.irregular_item import (
    IrregularEntryKind,
    IrregularFundEntry,
    IrregularFundingCreate,
    IrregularFundPlan,
    IrregularItemCreate,
    IrregularItemResponse,
    IrregularItemUpdate,
    IrregularPaymentCreate,
)
from kaleta.schemas.planned_transaction import PlannedTransactionCreate
from kaleta.schemas.transaction import TransactionCreate
from kaleta.services.account_service import AccountService
from kaleta.services.planned_transaction_service import PlannedTransactionService
from kaleta.services.text_order import text_key
from kaleta.services.transaction_service import TransactionService

#: Rows of the fund's history the page shows, newest first.
HISTORY_LIMIT = 100


class IrregularItemService:
    HISTORY_LIMIT = HISTORY_LIMIT

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── The fund ──────────────────────────────────────────────────────────

    async def _fund(self, fund_id: int) -> ReserveFund:
        fund = await self.session.get(ReserveFund, fund_id)
        if fund is None:
            raise NotFoundError(f"Fund {fund_id} not found.")
        if fund.kind is not ReserveFundKind.IRREGULAR:
            raise ValidationError("Only an irregular-expenses fund has items.")
        return fund

    async def items(self, fund_id: int) -> builtins.list[IrregularItem]:
        """The fund's items, by due month (a cost without one last), then by name."""
        await self._fund(fund_id)
        result = await self.session.execute(
            select(IrregularItem).where(IrregularItem.fund_id == fund_id)
        )
        return sorted(
            result.scalars().all(),
            key=lambda i: (i.due_month is None, i.due_month or 0, text_key(i.name)),
        )

    async def plan(self, fund_id: int) -> IrregularFundPlan:
        """The fund's items and what they ask for: ``KAL-IRR-001``, ``-002``."""
        fund = await self._fund(fund_id)
        items = [IrregularItemResponse.model_validate(i) for i in await self.items(fund_id)]
        return IrregularFundPlan(
            fund_id=fund.id,
            fund_name=fund.name,
            backing_account_id=fund.backing_account_id,
            items=items,
            yearly_total=sum((i.yearly_amount for i in items), Decimal("0.00")),
            # The sum of what each row shows, so the column adds up on screen.
            monthly_total=sum((i.monthly_contribution for i in items), Decimal("0.00")),
            balance=(
                await AccountService(self.session).balance(fund.backing_account_id)
                if fund.backing_account_id is not None
                else Decimal("0.00")
            ),
        )

    # ── Items ─────────────────────────────────────────────────────────────

    async def create(self, fund_id: int, data: IrregularItemCreate) -> IrregularItem:
        await self._fund(fund_id)
        item = IrregularItem(fund_id=fund_id, **data.model_dump())
        self.session.add(item)
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def _item(self, item_id: int) -> IrregularItem:
        item = await self.session.get(IrregularItem, item_id)
        if item is None:
            raise NotFoundError(f"Item {item_id} not found.")
        return item

    async def update(self, item_id: int, data: IrregularItemUpdate) -> IrregularItem:
        item = await self._item(item_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            if field in ("name", "yearly_amount") and value is None:
                continue
            setattr(item, field, value)
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def delete(self, item_id: int) -> None:
        await self.session.delete(await self._item(item_id))
        await self.session.commit()

    # ── The funding proposal (``KAL-IRR-003``) ────────────────────────────

    async def create_funding_plan(
        self, fund_id: int, payload: IrregularFundingCreate
    ) -> PlannedTransaction:
        """A monthly planned transfer of the fund's contribution into its account.

        Planned transactions carry one account, so — as for the salary — the
        transfer sits on the account the money leaves, and the fund's account
        is named in the description.
        """
        plan = await self.plan(fund_id)
        if plan.backing_account_id is None:
            raise ValidationError("The fund needs an account before it can be fed.")
        if plan.monthly_total <= 0:
            raise ValidationError("Add an item before planning the monthly transfer.")
        if payload.from_account_id == plan.backing_account_id:
            raise ValidationError("The money has to come from another account than the fund's.")
        source = await self.session.get(Account, payload.from_account_id)
        target = await self.session.get(Account, plan.backing_account_id)
        if source is None or target is None:
            raise NotFoundError("Account not found.")
        description = f"{source.name} → {target.name}"

        planned = PlannedTransactionService(self.session)
        for existing in await planned.list():
            if (
                existing.is_active
                and existing.type is TransactionType.TRANSFER
                and existing.account_id == source.id
                and existing.amount == plan.monthly_total
                and existing.description == description
            ):
                raise ConflictError("This monthly transfer is already planned.")

        return await planned.create(
            PlannedTransactionCreate(
                name=plan.fund_name,
                amount=plan.monthly_total,
                type=TransactionType.TRANSFER,
                account_id=source.id,
                description=description,
                frequency=RecurrenceFrequency.MONTHLY,
                interval=1,
                start_date=payload.start_date,
                is_active=True,
            )
        )

    # ── Payments and the fund's history (``KAL-IRR-004``, ``-005``) ───────

    async def _fund_account(self, fund_id: int) -> int:
        fund = await self._fund(fund_id)
        if fund.backing_account_id is None:
            raise ValidationError("The fund has no account to pay from.")
        return fund.backing_account_id

    async def _fund_item(self, fund_id: int, item_id: int) -> IrregularItem:
        item = await self._item(item_id)
        if item.fund_id != fund_id:
            raise ValidationError("That item belongs to another fund.")
        return item

    async def record_payment(self, fund_id: int, data: IrregularPaymentCreate) -> Transaction:
        """An expense out of the fund's account, paying one item or none (unplanned)."""
        account_id = await self._fund_account(fund_id)
        item = await self._fund_item(fund_id, data.item_id) if data.item_id is not None else None
        category_id = data.category_id or (item.category_id if item is not None else None)
        if category_id is None:
            raise ValidationError("Choose a category for the payment.")
        description = data.description.strip() or (item.name if item is not None else "")
        tx = await TransactionService(self.session).create(
            TransactionCreate(
                account_id=account_id,
                category_id=category_id,
                amount=data.amount,
                type=TransactionType.EXPENSE,
                date=data.date,
                description=description,
            )
        )
        if item is not None:
            tx.irregular_item_id = item.id
            await self.session.commit()
        return tx

    async def link_payment(self, fund_id: int, transaction_id: int, item_id: int | None) -> None:
        """Say which item an expense on the fund's account paid; ``None`` makes it unplanned."""
        account_id = await self._fund_account(fund_id)
        tx = await self.session.get(Transaction, transaction_id)
        if tx is None:
            raise NotFoundError(f"Transaction {transaction_id} not found.")
        if tx.account_id != account_id or tx.type is not TransactionType.EXPENSE:
            raise ValidationError("Only an expense paid from the fund's account is a payment.")
        if item_id is not None:
            await self._fund_item(fund_id, item_id)
        tx.irregular_item_id = item_id
        await self.session.commit()

    async def history(self, fund_id: int) -> builtins.list[IrregularFundEntry]:
        """The fund's account's movements, newest first, each said for what it is."""
        account_id = await self._fund_account(fund_id)
        names = {i.id: i.name for i in await self.items(fund_id)}
        rows = await self.session.execute(
            select(Transaction)
            .where(Transaction.account_id == account_id)
            .order_by(Transaction.date.desc(), Transaction.id.desc())
            .limit(HISTORY_LIMIT)
        )
        return [self._entry(tx, names) for tx in rows.scalars().all()]

    @staticmethod
    def _entry(tx: Transaction, names: dict[int, str]) -> IrregularFundEntry:
        incoming = tx.type is TransactionType.INCOME or (
            tx.type is TransactionType.TRANSFER and tx.transfer_direction is TransferDirection.IN
        )
        item_id = tx.irregular_item_id if tx.irregular_item_id in names else None
        if incoming:
            kind = IrregularEntryKind.CONTRIBUTION
        elif tx.type is TransactionType.EXPENSE:
            kind = (
                IrregularEntryKind.PAYMENT if item_id is not None else IrregularEntryKind.UNPLANNED
            )
        else:
            kind = IrregularEntryKind.WITHDRAWAL
        return IrregularFundEntry(
            transaction_id=tx.id,
            date=tx.date,
            description=tx.description,
            amount=tx.amount if incoming else -tx.amount,
            kind=kind,
            item_id=item_id,
            item_name=names.get(item_id) if item_id is not None else None,
        )

    @staticmethod
    def monthly_contribution(yearly: Decimal) -> Decimal:
        """The ÷10 rule, for views that preview an amount being typed."""
        return monthly_contribution(yearly)
