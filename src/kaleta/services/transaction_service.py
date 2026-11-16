# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import builtins
import datetime
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import Select, event, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, selectinload

from kaleta.config import settings
from kaleta.core.weeks import DEFAULT_WEEK_START_MODE, WeekStartMode, week_bucket
from kaleta.db.tenant_context import current_tenant
from kaleta.exceptions import (
    ConflictError,
    KaletaError,
    NotFoundError,
    PayloadTooLargeError,
    StaleWriteError,
    ValidationError,
)
from kaleta.models.account import Account
from kaleta.models.category import Category, CategoryType
from kaleta.models.dismissed_transfer_pair import DismissedTransferPair
from kaleta.models.payee import Payee
from kaleta.models.planned_transaction import PlannedTransaction
from kaleta.models.tag import Tag
from kaleta.models.transaction import (
    Transaction,
    TransactionSplit,
    TransactionType,
    TransferDirection,
)
from kaleta.schemas.transaction import (
    TransactionCreate,
    TransactionSplitCreate,
    TransactionUpdate,
    TransferCreate,
)
from kaleta.services.audit_service import AuditService
from kaleta.services.currency_rate_service import CurrencyRateService
from kaleta.services.member_name_service import MemberNameService
from kaleta.services.payee_service import PayeeService

#: The most rows a text search reads (newest first). Descriptions are
#: encrypted, so the search decrypts and filters in Python; this bounds what
#: one keystroke in the search box can cost. Measured budget: see
#: ``tests/unit/services/test_transaction_search_budget.py`` and the plan's
#: Implementation notes.
SEARCH_SCAN_LIMIT = 100_000

#: ``Session.info`` key of the last search's matching ids (``_search_ids``).
_SEARCH_MEMO = "kaleta.transaction_search"


def _forget_search(session: Session, *_args: object) -> None:
    session.info.pop(_SEARCH_MEMO, None)


# Any flush may have changed what a search would find; so may a rollback.
event.listen(Session, "after_flush", _forget_search)
event.listen(Session, "after_soft_rollback", _forget_search)

LEDGER_CSV_HEADERS: tuple[str, ...] = (
    "date",
    "type",
    "amount",
    "currency",
    "account",
    "category",
    "payee",
    "description",
    "tags",
    "is_internal_transfer",
)


#: How many days apart the two legs of a suggested transfer may be.
DEFAULT_TRANSFER_PAIRING_DAYS = 3
#: How far apart two legs' amounts may be and still pair, in the account's
#: currency: one grosz/cent absorbs a bank rounding. One value for the
#: suggester, accepting a suggestion, pairing by hand and linking through PUT.
DEFAULT_TRANSFER_AMOUNT_TOLERANCE = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class TransferPairSuggestion:
    """Two existing rows that look like one transfer between own accounts."""

    outgoing_id: int
    incoming_id: int
    amount: Decimal
    currency: str
    outgoing_account_id: int
    incoming_account_id: int
    outgoing_account: str
    incoming_account: str
    outgoing_date: datetime.date
    incoming_date: datetime.date
    outgoing_amount: Decimal
    incoming_amount: Decimal
    outgoing_description: str
    incoming_description: str

    @classmethod
    def from_legs(cls, outgoing: Transaction, incoming: Transaction) -> TransferPairSuggestion:
        return cls(
            outgoing_id=outgoing.id,
            incoming_id=incoming.id,
            amount=abs(outgoing.amount),
            currency=outgoing.account.currency,
            outgoing_account_id=outgoing.account_id,
            incoming_account_id=incoming.account_id,
            outgoing_account=outgoing.account.name,
            incoming_account=incoming.account.name,
            outgoing_date=outgoing.date,
            incoming_date=incoming.date,
            outgoing_amount=outgoing.amount,
            incoming_amount=incoming.amount,
            outgoing_description=outgoing.description,
            incoming_description=incoming.description,
        )


def transfer_pair_key(id_a: int, id_b: int) -> tuple[int, int]:
    """Order-independent key of a pair: lowest id first."""
    return (id_a, id_b) if id_a < id_b else (id_b, id_a)


class TransactionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _base_stmt(
        self,
        account_ids: builtins.list[int] | None = None,
        category_ids: builtins.list[int] | None = None,
        date_from: datetime.date | None = None,
        date_to: datetime.date | None = None,
        tx_types: builtins.list[TransactionType] | None = None,
        search: str | None = None,
        tag_ids: builtins.list[int] | None = None,
        user_ids: builtins.list[int] | None = None,
    ) -> Select[Transaction]:
        """Every filter that SQL can answer. ``search`` is not one of them (see
        :meth:`_search_ids`); the parameter stays so every caller passes the
        same arguments to ``list`` and ``count``."""
        del search
        stmt = select(Transaction)
        if account_ids:
            stmt = stmt.where(Transaction.account_id.in_(account_ids))
        if category_ids:
            stmt = stmt.where(Transaction.category_id.in_(category_ids))
        if date_from is not None:
            stmt = stmt.where(Transaction.date >= date_from)
        if date_to is not None:
            stmt = stmt.where(Transaction.date <= date_to)
        if tx_types:
            stmt = stmt.where(Transaction.type.in_(tx_types))
        if tag_ids:
            stmt = stmt.where(Transaction.tags.any(Tag.id.in_(tag_ids)))
        if user_ids:
            # "Added by": the member the row was attributed to on create.
            stmt = stmt.where(Transaction.user_id.in_(user_ids))
        return stmt

    async def list(
        self,
        account_ids: builtins.list[int] | None = None,
        category_ids: builtins.list[int] | None = None,
        date_from: datetime.date | None = None,
        date_to: datetime.date | None = None,
        tx_types: builtins.list[TransactionType] | None = None,
        search: str | None = None,
        tag_ids: builtins.list[int] | None = None,
        limit: int = 50,
        offset: int = 0,
        user_ids: builtins.list[int] | None = None,
    ) -> builtins.list[Transaction]:
        base = self._base_stmt(
            account_ids, category_ids, date_from, date_to, tx_types, None, tag_ids, user_ids
        )
        stmt = base.options(
            selectinload(Transaction.account),
            selectinload(Transaction.category),
            selectinload(Transaction.payee),
            selectinload(Transaction.splits).selectinload(TransactionSplit.category),
            selectinload(Transaction.tags),
        ).order_by(Transaction.date.desc(), Transaction.id.desc())
        if search:
            # The page is cut from the ids that matched, in the same order SQL
            # would have given; only that page is loaded whole.
            page_ids = (await self._search_ids(base, search))[offset : offset + limit]
            if not page_ids:
                return []
            stmt = stmt.where(Transaction.id.in_(page_ids))
        else:
            stmt = stmt.limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return builtins.list(result.scalars().all())

    async def _search_ids(self, base: Select[Transaction], search: str) -> builtins.list[int]:
        """Ids of the rows under ``base`` whose description contains ``search``, newest first.

        Case-insensitive, like the ``ILIKE`` it replaces. Reads two columns of
        at most ``SEARCH_SCAN_LIMIT`` rows — never whole transactions — and
        tests the decrypted descriptions here, because in the database they are
        ciphertext.

        A page and its count ask the same question one after the other (the
        ledger view and ``GET /transactions`` both do), so the answer is kept
        on the session for the next call and dropped at its next flush — a
        write in between can never be answered from it.
        """
        compiled = base.compile()
        key = (str(compiled), repr(sorted(compiled.params.items())), search)
        memo: tuple[tuple[str, str, str], builtins.list[int]] | None = self.session.info.get(
            _SEARCH_MEMO
        )
        if memo is not None and memo[0] == key:
            return memo[1]
        needle = search.casefold()
        ids = base.with_only_columns(Transaction.id, Transaction.description).order_by(
            Transaction.date.desc(), Transaction.id.desc()
        )
        rows = await self.session.execute(ids.limit(SEARCH_SCAN_LIMIT))
        found = [tx_id for tx_id, description in rows.all() if needle in description.casefold()]
        self.session.info[_SEARCH_MEMO] = (key, found)
        return found

    async def count(
        self,
        account_ids: builtins.list[int] | None = None,
        category_ids: builtins.list[int] | None = None,
        date_from: datetime.date | None = None,
        date_to: datetime.date | None = None,
        tx_types: builtins.list[TransactionType] | None = None,
        search: str | None = None,
        tag_ids: builtins.list[int] | None = None,
        user_ids: builtins.list[int] | None = None,
    ) -> int:
        stmt = self._base_stmt(
            account_ids, category_ids, date_from, date_to, tx_types, None, tag_ids, user_ids
        )
        if search:
            return len(await self._search_ids(stmt, search))
        count_stmt = select(func.count()).select_from(stmt.subquery())
        result = await self.session.execute(count_stmt)
        return result.scalar_one()

    async def export_ledger_csv(self) -> bytes:
        """Export every transaction as UTF-8 CSV (spreadsheet / notebook friendly)."""
        import csv
        import io

        stmt = (
            self._base_stmt()
            .options(
                selectinload(Transaction.account),
                selectinload(Transaction.category),
                selectinload(Transaction.payee),
                selectinload(Transaction.tags),
                selectinload(Transaction.splits).selectinload(TransactionSplit.category),
            )
            .order_by(Transaction.date.asc(), Transaction.id.asc())
        )
        result = await self.session.execute(stmt)
        transactions = builtins.list(result.scalars().all())

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(LEDGER_CSV_HEADERS)
        for tx in transactions:
            writer.writerow(
                [
                    tx.date.isoformat(),
                    tx.type.value,
                    str(tx.amount),
                    tx.account.currency if tx.account else "",
                    tx.account.name if tx.account else "",
                    self.category_display_label(tx),
                    tx.payee.name if tx.payee else "",
                    tx.description or "",
                    ";".join(sorted(tag.name for tag in tx.tags)),
                    "true" if tx.is_internal_transfer else "false",
                ]
            )
        return buf.getvalue().encode("utf-8")

    @staticmethod
    def ledger_csv_filename() -> str:
        today = datetime.date.today().isoformat()
        return f"kaleta_ledger_{today}.csv"

    async def get(self, transaction_id: int) -> Transaction | None:
        stmt = (
            select(Transaction)
            .where(Transaction.id == transaction_id)
            .options(
                selectinload(Transaction.account),
                selectinload(Transaction.category),
                selectinload(Transaction.payee),
                selectinload(Transaction.splits).selectinload(TransactionSplit.category),
                selectinload(Transaction.tags),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def _load_tags(self, tag_ids: builtins.list[int]) -> builtins.list[Tag]:
        if not tag_ids:
            return []
        result = await self.session.execute(select(Tag).where(Tag.id.in_(tag_ids)))
        return builtins.list(result.scalars())

    async def _resolve_payee_id(self, data: TransactionCreate | TransactionUpdate) -> int | None:
        """Turn a typed payee name into an id, matching or creating the payee.

        An explicit ``payee_id`` always wins — the name is only the fallback for
        free text the user typed into the combobox.
        """
        if data.payee_id is not None or not data.payee_name:
            return data.payee_id
        payee = await PayeeService(self.session).match_or_create_from_name(data.payee_name)
        return payee.id

    async def _payee_tag_defaults(
        self, payee_id: int | None, tag_ids: builtins.list[int]
    ) -> builtins.list[int]:
        """Tags this payee was last booked with, when the caller supplied none.

        Tags only. The learned *category* is filled in the dialog instead
        (``PayeeService.last_used_for``), because a category can never be
        missing here: ``TransactionCreate`` rejects a non-split income/expense
        without one, and a split parent or a transfer must not carry one at all.

        Looked up *before* the insert on purpose — afterwards the row being
        created would be its own most-recent match.
        """
        if payee_id is None or tag_ids:
            return tag_ids
        last_used = await PayeeService(self.session).last_used_for(payee_id)
        if last_used is None:
            return tag_ids
        return builtins.list(last_used.tag_ids)

    async def create(self, data: TransactionCreate) -> Transaction:
        payee_id = await self._resolve_payee_id(data)
        tag_ids = await self._payee_tag_defaults(payee_id, builtins.list(data.tag_ids))
        # Load tags up-front so we can pass them to the constructor — assigning
        # to ``.tags`` post-insert would trigger a lazy-load of the (empty)
        # collection in sync context and raise MissingGreenlet.
        tags = await self._load_tags(tag_ids) if tag_ids else []
        values = data.model_dump(exclude={"splits", "tag_ids", "payee_name"})
        values["payee_id"] = payee_id
        transaction = Transaction(**values, tags=tags)
        self.session.add(transaction)
        await self.session.flush()
        for split_data in data.splits:
            split = TransactionSplit(transaction_id=transaction.id, **split_data.model_dump())
            self.session.add(split)
        await self.session.commit()
        # Re-fetch with eager-loaded relationships so the response serializer
        # never hits a lazy relationship outside of an async context.
        fetched = await self.get(transaction.id)
        if fetched is None:
            raise KaletaError(f"Transaction id={transaction.id} not found after commit")
        return fetched

    async def create_bulk(
        self, creates: builtins.list[TransactionCreate], *, commit: bool = True
    ) -> int:
        """Insert many simple transactions in a single commit (no splits, no tags).

        Significantly faster than calling ``create()`` in a loop — intended for CSV
        import where transactions have no splits and no tags.
        Returns the number of inserted rows. ``commit=False`` only stages them,
        for a caller that commits several writes as one (``ImportPipeline.apply``).
        """
        objects = [
            Transaction(**c.model_dump(exclude={"splits", "tag_ids", "payee_name"}))
            for c in creates
        ]
        self.session.add_all(objects)
        if commit:
            await self.session.commit()
        return len(objects)

    @staticmethod
    def _check_bulk_size(count: int) -> None:
        cap = settings.api_bulk_max_items
        if count > cap:
            raise PayloadTooLargeError(
                f"{count} items is over the limit of {cap} per request (KALETA_API_BULK_MAX_ITEMS)."
            )

    async def _missing_ids(self, model: Any, ids: set[int]) -> builtins.list[int]:
        """The ids in ``ids`` that ``model`` has no row for, in one query."""
        if not ids:
            return []
        found = set(
            (await self.session.execute(select(model.id).where(model.id.in_(ids)))).scalars()
        )
        return sorted(ids - found)

    async def create_many(self, creates: builtins.list[TransactionCreate]) -> builtins.list[int]:
        """Store many simple rows in one commit and return their ids, in order.

        All or nothing: every row is checked before any is written. Unlike
        ``create_bulk`` (the import pipeline's fast path, which trusts its
        input), a row that would lose data — splits, tags, a typed payee, a
        link — or that is a lone transfer leg is refused, and every referenced
        account, category, payee and planned transaction must exist.
        """
        self._check_bulk_size(len(creates))
        for index, row in enumerate(creates):
            if row.splits or row.tag_ids or row.payee_name or row.linked_transaction_id:
                raise ValidationError(
                    f"Row {index}: splits, tag_ids, payee_name and linked_transaction_id are "
                    "not supported in bulk; use POST /api/v1/transactions.",
                    code="unsupported_in_bulk",
                )
            if row.type == TransactionType.TRANSFER:
                raise ValidationError(
                    f"Row {index}: a transfer has two legs; "
                    "use POST /api/v1/transactions/transfers.",
                    code="unsupported_in_bulk",
                )
        references: builtins.list[tuple[Any, set[int], str, str]] = [
            (Account, {r.account_id for r in creates}, "Accounts", "unknown_account"),
            (
                Category,
                {r.category_id for r in creates if r.category_id is not None},
                "Categories",
                "unknown_category",
            ),
            (
                Payee,
                {r.payee_id for r in creates if r.payee_id is not None},
                "Payees",
                "unknown_payee",
            ),
            (
                PlannedTransaction,
                {r.planned_transaction_id for r in creates if r.planned_transaction_id is not None},
                "Planned transactions",
                "unknown_planned_transaction",
            ),
        ]
        for model, ids, label, code in references:
            missing = await self._missing_ids(model, ids)
            if missing:
                raise ValidationError(
                    f"{label} not found: {', '.join(map(str, missing))}.", code=code
                )
        category_ids = {r.category_id for r in creates if r.category_id is not None}
        if category_ids:
            stmt = select(Category).where(Category.id.in_(category_ids))
            types = {c.id: c.type for c in (await self.session.execute(stmt)).scalars()}
            for index, row in enumerate(creates):
                if row.category_id is not None and types[row.category_id].value != row.type.value:
                    raise ValidationError(
                        f"Row {index}: a {types[row.category_id].value} category cannot go on "
                        f"a {row.type.value} row.",
                        code="category_type_mismatch",
                    )
        objects = [
            Transaction(**c.model_dump(exclude={"splits", "tag_ids", "payee_name"}))
            for c in creates
        ]
        self.session.add_all(objects)
        await self.session.flush()
        new_ids = [obj.id for obj in objects]
        await self.session.commit()
        return new_ids

    async def create_transfer_between(
        self, data: TransferCreate
    ) -> tuple[Transaction, Transaction]:
        """Create a checked transfer, both legs in one commit, as the add dialog does.

        Within one currency both legs move ``amount``. Between two, an
        ``exchange_rate`` is required and the incoming leg is ``to_amount``, or
        ``amount × rate`` rounded half up to the cent; the rate is then
        recorded, as the dialog records it.
        """
        source = await self.session.get(Account, data.from_account_id)
        target = await self.session.get(Account, data.to_account_id)
        for account, account_id in ((source, data.from_account_id), (target, data.to_account_id)):
            if account is None:
                raise NotFoundError(f"Account {account_id} not found.")
        if source is None or target is None:  # narrowed above; keeps mypy honest
            raise NotFoundError("Account not found.")
        if source.id == target.id:
            raise ValidationError(
                "A transfer moves money between two different accounts.",
                message_key="errors.transaction.transfer_different_accounts",
            )
        rate = data.exchange_rate
        if source.currency == target.currency:
            if rate is not None:
                raise ValidationError(
                    "Both accounts use the same currency; leave exchange_rate out."
                )
            if data.to_amount is not None and data.to_amount != data.amount:
                raise ValidationError(
                    "Both accounts use the same currency; to_amount must equal amount."
                )
            incoming_amount = data.amount
        else:
            if rate is None:
                raise ValidationError(
                    f"A transfer from {source.currency} to {target.currency} needs an "
                    "exchange_rate."
                )
            incoming_amount = data.to_amount or (data.amount * rate).quantize(
                Decimal("0.01"), ROUND_HALF_UP
            )

        def leg(
            account_id: int, amount: Decimal, direction: TransferDirection
        ) -> TransactionCreate:
            return TransactionCreate(
                account_id=account_id,
                amount=amount,
                exchange_rate=rate,
                type=TransactionType.TRANSFER,
                transfer_direction=direction,
                date=data.date,
                description=data.description,
                notes=data.notes,
                is_internal_transfer=True,
            )

        legs = await self.create_transfer(
            leg(source.id, data.amount, TransferDirection.OUT),
            leg(target.id, incoming_amount, TransferDirection.IN),
        )
        if rate is not None:
            await CurrencyRateService(self.session).record_transfer_rate(
                data.date, source.currency, target.currency, rate
            )
        return legs

    async def create_transfer(
        self,
        outgoing: TransactionCreate,
        incoming: TransactionCreate,
    ) -> tuple[Transaction, Transaction]:
        """Create a paired internal transfer (two linked legs) atomically.

        The legs' directions come from their position, whatever the payloads
        say: the first is where the money left, the second where it arrived.
        """
        excluded = {"splits", "tag_ids", "payee_name", "transfer_direction"}
        tx_out = Transaction(
            **outgoing.model_dump(exclude=excluded), transfer_direction=TransferDirection.OUT
        )
        self.session.add(tx_out)
        await self.session.flush()  # get tx_out.id

        tx_in = Transaction(
            **incoming.model_dump(exclude=excluded), transfer_direction=TransferDirection.IN
        )
        tx_in.linked_transaction_id = tx_out.id
        self.session.add(tx_in)
        await self.session.flush()  # get tx_in.id

        tx_out.linked_transaction_id = tx_in.id
        await self.session.commit()
        fetched_out = await self.get(tx_out.id)
        fetched_in = await self.get(tx_in.id)
        if fetched_out is None or fetched_in is None:
            raise KaletaError("Transfer legs not found after commit")
        return fetched_out, fetched_in

    async def pair_as_transfer(
        self,
        expense_id: int,
        income_id: int,
        *,
        amount_tolerance: Decimal = DEFAULT_TRANSFER_AMOUNT_TOLERANCE,
    ) -> tuple[Transaction, Transaction]:
        """Turn two existing rows into the two legs of one internal transfer.

        The common import mess: money moved between two of the user's own
        accounts arrives as an ordinary expense on one statement and an
        ordinary income on the other, and both inflate the totals. The rows
        stay where they are — same accounts, dates, descriptions — and only
        become what they were: type ``transfer``, flagged internal, linked to
        each other, with no category.

        ``expense_id`` is the leg the money left, ``income_id`` the leg it
        arrived on. A leg already typed ``transfer`` (an import that
        recognised one side) may stand on either side; an income cannot be
        the outgoing leg, nor an expense the incoming one.
        """
        if expense_id == income_id:
            raise ValidationError(
                "A transfer needs two different transactions.",
                message_key="errors.transaction.transfer_needs_two_rows",
            )
        outgoing = await self.get(expense_id)
        incoming = await self.get(income_id)
        if outgoing is None:
            raise NotFoundError(
                f"Transaction {expense_id} not found.",
                message_key="errors.transaction.not_found_id",
                params={"transaction_id": expense_id},
            )
        if incoming is None:
            raise NotFoundError(
                f"Transaction {income_id} not found.",
                message_key="errors.transaction.not_found_id",
                params={"transaction_id": income_id},
            )
        # ``get`` eager-loads ``account``; the currency check below reads it.
        self._validate_transfer_pair(outgoing, incoming, amount_tolerance)
        self._link_transfer_legs(outgoing, incoming)
        await self.session.commit()
        fetched_out = await self.get(expense_id)
        fetched_in = await self.get(income_id)
        if fetched_out is None or fetched_in is None:
            raise KaletaError("Transfer legs not found after commit")
        return fetched_out, fetched_in

    async def pair_selected_as_transfer(
        self, first_id: int, second_id: int
    ) -> tuple[Transaction, Transaction]:
        """Pair two rows given in any order; return ``(outgoing, incoming)``.

        The ledger's "Mark as transfer" and ``POST /api/v1/transfer-pairs``
        know two ids, not which leg is which; the rows' own types say that
        (see :meth:`orient_transfer_legs`). Two rows already linked to each
        other are returned unchanged, so a retried request is safe.
        """
        if first_id == second_id:
            raise ValidationError(
                "A transfer needs two different transactions.",
                message_key="errors.transaction.transfer_needs_two_rows",
            )
        first = await self._get_or_raise(first_id)
        second = await self._get_or_raise(second_id)
        if first.linked_transaction_id == second.id and second.linked_transaction_id == first.id:
            linked = self._orient_linked_legs(first, second)
            if linked is not None:
                return linked
        oriented = self.orient_transfer_legs(first, second)
        if oriented is None:
            raise ValidationError(
                "A transfer needs money leaving one account and entering another.",
                message_key="errors.transaction.transfer_needs_both_directions",
            )
        outgoing, incoming = oriented
        return await self.pair_as_transfer(outgoing.id, incoming.id)

    async def _get_or_raise(self, transaction_id: int) -> Transaction:
        transaction = await self.get(transaction_id)
        if transaction is None:
            raise NotFoundError(
                f"Transaction {transaction_id} not found.",
                message_key="errors.transaction.not_found_id",
                params={"transaction_id": transaction_id},
            )
        return transaction

    @staticmethod
    def _orient_linked_legs(
        row_a: Transaction, row_b: Transaction
    ) -> tuple[Transaction, Transaction] | None:
        """``(outgoing, incoming)`` of a linked pair, from the legs' directions."""
        if row_a.transfer_direction == TransferDirection.OUT == row_b.transfer_direction:
            return None
        if row_a.transfer_direction == TransferDirection.OUT:
            return row_a, row_b
        if row_b.transfer_direction == TransferDirection.OUT:
            return row_b, row_a
        return None

    @staticmethod
    def _link_transfer_legs(outgoing: Transaction, incoming: Transaction) -> None:
        """Write both sides of one transfer: type, direction, flag, no category, links."""
        for leg, direction in (
            (outgoing, TransferDirection.OUT),
            (incoming, TransferDirection.IN),
        ):
            leg.type = TransactionType.TRANSFER
            leg.transfer_direction = direction
            leg.is_internal_transfer = True
            leg.category_id = None
        outgoing.linked_transaction_id = incoming.id
        incoming.linked_transaction_id = outgoing.id

    # ── Transfer suggestions ─────────────────────────────────────────────────

    async def suggest_transfer_pairs(
        self,
        *,
        max_days_apart: int = DEFAULT_TRANSFER_PAIRING_DAYS,
        amount_tolerance: Decimal = DEFAULT_TRANSFER_AMOUNT_TOLERANCE,
        date_from: datetime.date | None = None,
        date_to: datetime.date | None = None,
    ) -> builtins.list[TransferPairSuggestion]:
        """Find pairs of unlinked rows that look like one transfer between own accounts.

        Two rows are a candidate pair when they sit on different accounts in
        the same currency, carry the same amount (within ``amount_tolerance``),
        are at most ``max_days_apart`` days apart and point in opposite
        directions: an expense with an income, or a row an import already
        typed ``transfer`` with an expense, an income or another such row.
        Two expenses (or two incomes) are never a transfer.

        Nothing is written: the caller shows the pairs and the user accepts
        (:meth:`accept_transfer_pair`) or dismisses
        (:meth:`dismiss_transfer_pair`) each one. A dismissed pair is never
        suggested again. Every row appears in at most one suggestion; when a
        row could pair with several, the closest date wins.

        ``date_from`` / ``date_to`` bound the rows considered — the import
        review passes the span of the rows it just imported, widened by the
        window, so years of unrelated history are not offered at once.
        """
        stmt = (
            select(Transaction)
            .options(selectinload(Transaction.account))
            .where(
                Transaction.linked_transaction_id.is_(None),
                Transaction.is_split.is_(False),
            )
            .order_by(Transaction.amount, Transaction.date, Transaction.id)
        )
        if date_from is not None:
            stmt = stmt.where(Transaction.date >= date_from)
        if date_to is not None:
            stmt = stmt.where(Transaction.date <= date_to)
        rows = builtins.list((await self.session.execute(stmt)).scalars().all())
        dismissed = await self._dismissed_transfer_pairs()

        # Sorted by amount, so every partner of a row lies in the short run
        # after it whose amounts are still within tolerance. Amounts are
        # stored unsigned (direction lives in ``type``), which is what lets an
        # expense and an income of the same size sit next to each other here.
        candidates: builtins.list[tuple[int, Decimal, int, int, Transaction, Transaction]] = []
        for i, row_a in enumerate(rows):
            for row_b in rows[i + 1 :]:
                amount_gap = abs(row_b.amount - row_a.amount)
                if amount_gap > amount_tolerance:
                    break
                day_gap = abs((row_a.date - row_b.date).days)
                if day_gap > max_days_apart:
                    continue
                oriented = self._orient_candidate(row_a, row_b)
                if oriented is None:
                    continue
                outgoing, incoming = oriented
                if transfer_pair_key(outgoing.id, incoming.id) in dismissed:
                    continue
                candidates.append(
                    (day_gap, amount_gap, outgoing.id, incoming.id, outgoing, incoming)
                )

        candidates.sort(key=lambda c: (c[0], c[1], c[2], c[3]))
        taken: set[int] = set()
        suggestions: builtins.list[TransferPairSuggestion] = []
        for _day_gap, _amount_gap, out_id, in_id, outgoing, incoming in candidates:
            if out_id in taken or in_id in taken:
                continue
            taken.update((out_id, in_id))
            suggestions.append(TransferPairSuggestion.from_legs(outgoing, incoming))
        suggestions.sort(key=lambda s: (s.outgoing_date, s.outgoing_id))
        return suggestions

    @classmethod
    def _orient_candidate(
        cls, row_a: Transaction, row_b: Transaction
    ) -> tuple[Transaction, Transaction] | None:
        """Return ``(outgoing, incoming)`` when the two rows can be one transfer."""
        if row_a.account_id == row_b.account_id:
            return None
        if row_a.account.currency != row_b.account.currency:
            return None
        return cls.orient_transfer_legs(row_a, row_b)

    async def _dismissed_transfer_pairs(self) -> set[tuple[int, int]]:
        result = await self.session.execute(
            select(
                DismissedTransferPair.first_transaction_id,
                DismissedTransferPair.second_transaction_id,
            )
        )
        return {(int(first), int(second)) for first, second in result.all()}

    async def accept_transfer_pair(
        self,
        outgoing_id: int,
        incoming_id: int,
        *,
        amount_tolerance: Decimal = DEFAULT_TRANSFER_AMOUNT_TOLERANCE,
    ) -> tuple[Transaction, Transaction]:
        """Make a suggested pair one transfer (see :meth:`pair_as_transfer`)."""
        return await self.pair_as_transfer(
            outgoing_id, incoming_id, amount_tolerance=amount_tolerance
        )

    async def dismiss_transfer_pair(self, first_id: int, second_id: int) -> None:
        """Remember that these two rows are not one transfer. Idempotent.

        Both rows are looked up first, so an unknown id is a ``NotFoundError``
        rather than a foreign-key failure at commit.
        """
        if first_id == second_id:
            raise ValidationError(
                "A transfer needs two different transactions.",
                message_key="errors.transaction.transfer_needs_two_rows",
            )
        await self._get_or_raise(first_id)
        await self._get_or_raise(second_id)
        first, second = transfer_pair_key(first_id, second_id)
        existing = await self.session.execute(
            select(DismissedTransferPair.id).where(
                DismissedTransferPair.first_transaction_id == first,
                DismissedTransferPair.second_transaction_id == second,
            )
        )
        if existing.scalar_one_or_none() is not None:
            return
        self.session.add(
            DismissedTransferPair(first_transaction_id=first, second_transaction_id=second)
        )
        await self.session.commit()

    async def set_category_bulk(self, transaction_ids: builtins.list[int], category_id: int) -> int:
        """Assign one category to many rows at once; return how many changed.

        The ledger's multi-select recategorises a batch of similar rows in a
        single step. The category's type has to match every row's — an expense
        category cannot land on an income — and split rows carry a category per
        line, so neither can take one here. Both are refused for the whole
        batch rather than applied in part, so the user is never left guessing
        which of the selected rows actually moved.
        """
        if not transaction_ids:
            return 0
        wanted_ids = set(transaction_ids)
        self._check_bulk_size(len(wanted_ids))
        category = await self.session.get(Category, category_id)
        if category is None:
            raise NotFoundError(
                f"Category {category_id} not found.",
                message_key="errors.transaction.category_not_found",
                params={"category_id": category_id},
            )
        if category.type not in (CategoryType.INCOME, CategoryType.EXPENSE):
            raise ValidationError(
                "Only income and expense categories can be assigned.",
                message_key="errors.transaction.only_income_expense_categories",
            )
        stmt = select(Transaction).where(Transaction.id.in_(transaction_ids))
        transactions = builtins.list((await self.session.execute(stmt)).scalars().all())
        missing = sorted(wanted_ids - {tx.id for tx in transactions})
        if missing:
            # A row deleted meanwhile must not turn the batch into a partial move.
            raise NotFoundError(f"Transactions not found: {', '.join(map(str, missing))}.")
        wanted = TransactionType(category.type.value)
        for tx in transactions:
            if tx.is_split:
                raise ValidationError(
                    "A split transaction's category is set per line, not in bulk.",
                    message_key="errors.transaction.split_category_per_line",
                )
            if tx.type != wanted:
                raise ValidationError(
                    f"A {category.type.value} category can only go on {category.type.value} rows.",
                    message_key="errors.transaction.category_type_mismatch",
                    params={"category_type": category.type.value},
                )
        for tx in transactions:
            tx.category_id = category_id
        await self.session.commit()
        return len(transactions)

    @staticmethod
    def orient_transfer_legs(
        row_a: Transaction, row_b: Transaction
    ) -> tuple[Transaction, Transaction] | None:
        """Return ``(outgoing, incoming)``, or ``None`` when the types cannot pair.

        An income is always the incoming leg and an expense always the
        outgoing one; two expenses (or two incomes) are never a transfer. Two
        rows already typed ``transfer`` carry no direction, so the lower id
        goes first — the order a manually entered transfer's legs are saved in.
        """
        types = (row_a.type, row_b.type)
        if types in (
            (TransactionType.INCOME, TransactionType.INCOME),
            (TransactionType.EXPENSE, TransactionType.EXPENSE),
        ):
            return None
        if row_a.type == TransactionType.INCOME or row_b.type == TransactionType.EXPENSE:
            return row_b, row_a
        if row_a.type == TransactionType.EXPENSE or row_b.type == TransactionType.INCOME:
            return row_a, row_b
        return (row_a, row_b) if row_a.id < row_b.id else (row_b, row_a)

    @staticmethod
    def _validate_transfer_pair(
        outgoing: Transaction, incoming: Transaction, amount_tolerance: Decimal
    ) -> None:
        if outgoing.type == TransactionType.INCOME:
            raise ValidationError(
                "The outgoing leg of a transfer cannot be an income.",
                message_key="errors.transaction.outgoing_leg_not_income",
            )
        if incoming.type == TransactionType.EXPENSE:
            raise ValidationError(
                "The incoming leg of a transfer cannot be an expense.",
                message_key="errors.transaction.incoming_leg_not_expense",
            )
        if outgoing.account_id == incoming.account_id:
            raise ValidationError(
                "A transfer moves money between two different accounts.",
                message_key="errors.transaction.transfer_different_accounts",
            )
        if outgoing.account.currency != incoming.account.currency:
            raise ValidationError(
                "Pairing rows in different currencies is not supported.",
                message_key="errors.transaction.transfer_currency_mismatch",
            )
        if abs(abs(outgoing.amount) - abs(incoming.amount)) > amount_tolerance:
            raise ValidationError(
                "Both legs of a transfer must have the same amount.",
                message_key="errors.transaction.transfer_amount_mismatch",
            )
        for leg, other in ((outgoing, incoming), (incoming, outgoing)):
            # Already linked to each other is not a conflict: it is the pair
            # being re-stated (a retried request, a PUT naming the same leg).
            if leg.linked_transaction_id not in (None, other.id):
                raise ConflictError(
                    f"Transaction {leg.id} is already linked to another row.",
                    message_key="errors.transaction.already_linked",
                    params={"transaction_id": leg.id},
                )
            if leg.is_split:
                raise ValidationError(
                    "A split transaction cannot be part of a transfer.",
                    message_key="errors.transaction.split_cannot_be_transfer",
                )

    @staticmethod
    def _validate_split_sum(amount: Decimal, splits: builtins.list[TransactionSplitCreate]) -> None:
        if not splits:
            raise ValidationError(
                "Split transactions must have at least one split.",
                message_key="errors.transaction.split_needs_at_least_one",
            )
        split_total = sum((s.amount for s in splits), start=Decimal("0"))
        if split_total != amount:
            remaining = amount - split_total
            raise ValidationError(
                f"Split amounts must sum to {amount}; {remaining:+.2f} remaining.",
                message_key="errors.transaction.split_sum_mismatch",
                params={"amount": amount, "remaining": remaining},
            )

    async def update(self, transaction_id: int, data: TransactionUpdate) -> Transaction | None:
        transaction = await self.get(transaction_id)
        if transaction is None:
            return None
        await self._refuse_stale_write(transaction, data.expected_updated_at)
        fields_set = data.model_fields_set
        updates = data.model_dump(
            exclude_unset=True,
            exclude={
                "splits",
                "is_split",
                "tag_ids",
                "payee_name",
                "expected_updated_at",
                "linked_transaction_id",
            },
        )
        # A typed payee resolves to an id here too, so the edit dialog can name a
        # payee that does not exist yet. No learned defaults on update: the row
        # already has the values the user chose, and we do not overwrite them.
        if data.payee_name:
            updates["payee_id"] = await self._resolve_payee_id(data)
        splits = data.splits if "splits" in fields_set else None
        is_split = data.is_split if "is_split" in fields_set else None
        tag_ids = data.tag_ids if "tag_ids" in fields_set else None

        if (
            transaction.is_split
            and "amount" in updates
            and updates["amount"] != transaction.amount
            and splits is None
        ):
            raise ValidationError(
                "Cannot change amount on a split transaction without updating splits.",
                message_key="errors.transaction.split_amount_needs_splits",
            )

        effective_type = (
            data.type if "type" in fields_set and data.type is not None else transaction.type
        )
        if (
            is_split is False
            and transaction.is_split
            and effective_type in (TransactionType.INCOME, TransactionType.EXPENSE)
            and ("category_id" not in fields_set or data.category_id is None)
        ):
            raise ValidationError(
                f"{effective_type.value.capitalize()} transactions require a category.",
                message_key="errors.transaction.type_requires_category",
                params={"transaction_type": effective_type.value.capitalize()},
            )

        previous_type = transaction.type
        for field, value in updates.items():
            setattr(transaction, field, value)
        self._settle_transfer_direction(transaction, previous_type)

        if is_split is not None:
            transaction.is_split = is_split
            if is_split:
                transaction.category_id = None
            elif transaction.splits:
                transaction.splits.clear()

        if splits is not None:
            self._validate_split_sum(transaction.amount, splits)
            transaction.is_split = True
            transaction.category_id = None
            transaction.splits.clear()
            for split_data in splits:
                transaction.splits.append(TransactionSplit(**split_data.model_dump()))

        await self._apply_link_update(transaction, data, previous_type)

        if tag_ids is not None:
            transaction.tags = await self._load_tags(tag_ids)
        await self.session.commit()
        return await self.get(transaction_id)

    async def _apply_link_update(
        self, transaction: Transaction, data: TransactionUpdate, previous_type: TransactionType
    ) -> None:
        """Keep a transfer link two-sided and valid when an update touches it.

        Runs after the other fields are applied, so the checks see the row as
        it is about to be saved. Three cases:

        - the update names a new partner: the pair is validated as
          :meth:`pair_as_transfer` does (accounts, currency, amount, roles,
          neither leg linked elsewhere) and both legs are written;
        - the update clears the link: the partner's link back is cleared too
          (both rows stay transfers; turning one back into an expense or an
          income is an edit of its own);
        - a linked row is turned into a transfer: the pair is validated and
          both legs written, as for a new partner.
        """
        current = transaction.linked_transaction_id
        if "linked_transaction_id" in data.model_fields_set:
            wanted = data.linked_transaction_id
            if wanted is None:
                if current is not None:
                    await self._clear_link(transaction, current)
                return
            if wanted != current:
                await self._link_by_update(transaction, wanted)
                return
        if (
            current is not None
            and transaction.type == TransactionType.TRANSFER
            and previous_type != TransactionType.TRANSFER
        ):
            await self._link_by_update(transaction, current)

    async def _clear_link(self, transaction: Transaction, partner_id: int) -> None:
        transaction.linked_transaction_id = None
        partner = await self.session.get(Transaction, partner_id)
        if partner is not None and partner.linked_transaction_id == transaction.id:
            partner.linked_transaction_id = None

    async def _link_by_update(self, transaction: Transaction, partner_id: int) -> None:
        # The row already carries the update's fields; a lookup below must not
        # flush them first (a missing account would surface as a foreign-key
        # error instead of ``account_not_found``). Nothing is written until the
        # checks pass.
        with self.session.no_autoflush:
            await self._check_and_link(transaction, partner_id)

    async def _check_and_link(self, transaction: Transaction, partner_id: int) -> None:
        if partner_id == transaction.id:
            raise ValidationError(
                "A transfer needs two different transactions.",
                message_key="errors.transaction.transfer_needs_two_rows",
            )
        partner = await self._get_or_raise(partner_id)
        oriented = self._orient_for_link(transaction, partner)
        if oriented is None:
            raise ValidationError(
                "A transfer needs money leaving one account and entering another.",
                message_key="errors.transaction.transfer_needs_both_directions",
            )
        outgoing, incoming = oriented
        if transaction.account_id != transaction.account.id:
            # The update moved the row to another account; the currency check
            # must read the new one, not the account loaded with the row.
            account = await self.session.get(Account, transaction.account_id)
            if account is None:
                raise NotFoundError(
                    f"Account {transaction.account_id} not found.",
                    message_key="errors.transaction.account_not_found",
                    params={"account_id": transaction.account_id},
                )
            transaction.account = account
        self._validate_transfer_pair(outgoing, incoming, DEFAULT_TRANSFER_AMOUNT_TOLERANCE)
        self._link_transfer_legs(outgoing, incoming)

    @classmethod
    def _orient_for_link(
        cls, row: Transaction, partner: Transaction
    ) -> tuple[Transaction, Transaction] | None:
        """``(outgoing, incoming)`` for a link set through an update.

        A transfer leg that already says which way its money went decides the
        roles; two legs that both say the same way cannot be one transfer.
        Otherwise the types decide, as in :meth:`orient_transfer_legs`.
        """
        directed = [
            leg
            for leg in (row, partner)
            if leg.type == TransactionType.TRANSFER and leg.transfer_direction is not None
        ]
        if len(directed) == 2 and row.transfer_direction == partner.transfer_direction:
            return None
        if directed:
            leg = directed[0]
            other = partner if leg is row else row
            return (leg, other) if leg.transfer_direction == TransferDirection.OUT else (other, leg)
        return cls.orient_transfer_legs(row, partner)

    async def _refuse_stale_write(
        self, transaction: Transaction, expected: datetime.datetime | None
    ) -> None:
        """Refuse an edit made over a version of the row that is no longer current.

        Two members of a household can open the same row; the second save
        would silently undo the first. The row is locked first, so a save in
        flight elsewhere finishes before the comparison is made.
        """
        if expected is None:
            return
        current = await self.session.scalar(
            select(Transaction.updated_at).where(Transaction.id == transaction.id).with_for_update()
        )
        if current is None or current == expected:
            return
        changed_by: str | None = None
        user_id = await AuditService(self.session).last_changed_by("transactions", transaction.id)
        ctx = current_tenant()
        acting = ctx.member_user_id if ctx is not None else None
        # Their own save in another tab is "elsewhere", not "by <themselves>".
        if user_id is not None and user_id != acting:
            changed_by = (await MemberNameService(self.session).names()).get(user_id)
        if changed_by:
            raise StaleWriteError(
                f"This transaction was changed by {changed_by} a moment ago.",
                changed_by=changed_by,
                message_key="errors.transaction.stale_write_by_member",
                params={"changed_by": changed_by},
            )
        raise StaleWriteError(
            "This transaction was changed elsewhere a moment ago.",
            changed_by=changed_by,
            message_key="errors.transaction.stale_write_elsewhere",
        )

    @staticmethod
    def _settle_transfer_direction(
        transaction: Transaction, previous_type: TransactionType
    ) -> None:
        """Keep ``transfer_direction`` consistent with the row's (new) type.

        Only a transfer leg has a direction. A row edited into a transfer
        without saying which way keeps the way its money already went (an
        expense left the account, an income arrived), so the balance does not
        move just because the type changed.
        """
        if transaction.type != TransactionType.TRANSFER:
            transaction.transfer_direction = None
            return
        if transaction.transfer_direction is not None:
            return
        if previous_type == TransactionType.INCOME:
            transaction.transfer_direction = TransferDirection.IN
        elif previous_type == TransactionType.EXPENSE:
            transaction.transfer_direction = TransferDirection.OUT
        else:
            raise ValidationError(
                "A transfer leg needs transfer_direction ('out' or 'in').",
                message_key="errors.transaction.transfer_leg_needs_direction",
            )

    async def delete(self, transaction_id: int) -> bool:
        transaction = await self.get(transaction_id)
        if transaction is None:
            return False
        await self.session.delete(transaction)
        await self.session.commit()
        return True

    @staticmethod
    def category_display_label(transaction: Transaction) -> str:
        """Human-readable category for CSV / exports (lists split category names)."""
        if transaction.is_split and transaction.splits:
            names = [s.category.name for s in transaction.splits if s.category]
            return f"(Split: {', '.join(names)})" if names else "(Split)"
        return transaction.category.name if transaction.category else "—"

    @staticmethod
    def split_lines_summary(transaction: Transaction) -> str:
        """Tooltip text listing split amounts and category names (locale-neutral)."""
        if not transaction.is_split or not transaction.splits:
            return ""
        parts: builtins.list[str] = []
        for split in transaction.splits:
            name = split.category.name if split.category else "—"
            parts.append(f"{split.amount:,.2f} {name}")
        return " · ".join(parts)

    @staticmethod
    def group_separator_label(
        tx_date: datetime.date,
        prev_date: datetime.date | None,
        grouping: str,
        week_mode: WeekStartMode = DEFAULT_WEEK_START_MODE,
    ) -> str:
        """Mark where a group of rows starts, and say which group it is.

        Which week a day belongs to is the user's setting, not a constant:
        ``kaleta.core.weeks`` owns both answers so this label and the band the
        view draws over it cannot come from two different calendars.
        """
        if grouping == "none":
            return ""
        if grouping == "week":
            bucket = week_bucket(tx_date, week_mode)
            label = f"W{bucket.index:02d} {bucket.start.year}"
            if prev_date is None:
                return label
            return label if bucket != week_bucket(prev_date, week_mode) else ""
        label = tx_date.strftime("%B %Y")
        if prev_date is None:
            return label
        return label if (tx_date.year, tx_date.month) != (prev_date.year, prev_date.month) else ""

    @staticmethod
    def short_date(day: datetime.date) -> str:
        """The date as the ledger's narrow date column shows it.

        One rule for every kind of row the column carries — a recorded one and
        an upcoming planned one sit under the same heading, so they cannot be
        allowed to drift into two formats.
        """
        return day.strftime("%d.%m")

    @staticmethod
    def signed_amount(
        amount: Decimal,
        tx_type: TransactionType,
        transfer_direction: TransferDirection | None = None,
    ) -> Decimal:
        """Money in as positive, money out as negative.

        The one place the ledger's sign convention lives, so a total under a
        column of figures cannot disagree with the figures themselves. Income
        is money in; expense is money out. A transfer leg goes either way
        according to ``transfer_direction`` — the incoming leg arrived on its
        account (positive), the outgoing leg left it (negative) — matching how
        ``AccountService.signed_ledger_amount`` moves the balance. A transfer
        with no direction given falls back to money out, the old behaviour.
        """
        if tx_type == TransactionType.INCOME:
            return abs(amount)
        if tx_type == TransactionType.TRANSFER and transfer_direction == TransferDirection.IN:
            return abs(amount)
        return -abs(amount)

    @staticmethod
    def format_signed_amount(
        amount: Decimal,
        tx_type: TransactionType,
        transfer_direction: TransferDirection | None = None,
    ) -> str:
        """The row's figure, signed — except zero, which has no direction."""
        return TransactionService.format_net(
            TransactionService.signed_amount(amount, tx_type, transfer_direction)
        )

    @staticmethod
    def format_net(net: Decimal) -> str:
        """A group's net, signed the same way its rows are.

        Zero carries no sign: nothing moved, so there is no direction to show.
        """
        return f"{net:,.2f}" if net == 0 else f"{net:+,.2f}"

    @staticmethod
    def split_balance(
        main_amount: Decimal, split_amounts: builtins.list[Decimal]
    ) -> tuple[bool, Decimal]:
        total_split = sum(split_amounts, start=Decimal("0"))
        remaining = main_amount - total_split
        return remaining == Decimal("0"), remaining

    @staticmethod
    def build_table_row(
        transaction: Transaction,
        prev_transaction: Transaction | None,
        grouping: str,
        week_mode: WeekStartMode = DEFAULT_WEEK_START_MODE,
    ) -> dict[str, Any]:
        prev_date = prev_transaction.date if prev_transaction else None
        has_splits = bool(transaction.is_split and transaction.splits)
        split_count = len(transaction.splits) if has_splits else 0
        if has_splits:
            # English fallback; views.attach_split_labels overwrites with t().
            category = f"Split ({split_count})"
            split_tooltip = TransactionService.split_lines_summary(transaction)
        else:
            category = transaction.category.name if transaction.category else "—"
            split_tooltip = ""
        return {
            "id": transaction.id,
            "user_id": transaction.user_id,
            "date": str(transaction.date),
            # The ledger shows DD.MM; the ISO value stays for sorting and tooltips.
            "date_short": TransactionService.short_date(transaction.date),
            "account": transaction.account.name if transaction.account else "—",
            "description": (transaction.description or "—")[:55],
            "notes": transaction.notes or "",
            "has_notes": bool(transaction.notes),
            "category": category,
            "has_splits": has_splits,
            "split_count": split_count,
            "split_tooltip": split_tooltip,
            "type": transaction.type.value,
            "amount": TransactionService.format_signed_amount(
                transaction.amount, transaction.type, transaction.transfer_direction
            ),
            # Kept beside the formatted string so a selection total can be summed
            # without parsing it back out of the display.
            "amount_value": str(
                TransactionService.signed_amount(
                    transaction.amount, transaction.type, transaction.transfer_direction
                )
            ),
            "tags": "",
            "tags_data": [
                {
                    "id": tg.id,
                    "name": tg.name,
                    "color": tg.color or "#9E9E9E",
                    "icon": tg.icon or "label",
                }
                for tg in transaction.tags
            ],
            "sep_label": TransactionService.group_separator_label(
                transaction.date, prev_date, grouping, week_mode
            ),
        }

    @staticmethod
    def build_table_rows(
        transactions: builtins.list[Transaction],
        grouping: str,
        week_mode: WeekStartMode = DEFAULT_WEEK_START_MODE,
    ) -> builtins.list[dict[str, Any]]:
        rows: builtins.list[dict[str, Any]] = []
        for i, tx in enumerate(transactions):
            prev_tx = transactions[i - 1] if i > 0 else None
            rows.append(TransactionService.build_table_row(tx, prev_tx, grouping, week_mode))
        return TransactionService.attach_group_nets(rows)

    @staticmethod
    def merge_upcoming_rows(
        actual_rows: builtins.list[dict[str, Any]],
        upcoming_rows: builtins.list[dict[str, Any]],
        grouping: str,
        week_mode: WeekStartMode = DEFAULT_WEEK_START_MODE,
    ) -> builtins.list[dict[str, Any]]:
        """One chronological feed of what happened and what is about to.

        Both sides are already shaped as table rows, so the merge is a re-sort:
        newest first, and on a day that holds both, the recorded rows come
        before the promised ones. The group separators have to be worked out
        again afterwards — they were computed over the actuals alone, and a
        planned row can open a week or a month of its own.
        """
        if not upcoming_rows:
            return actual_rows

        merged = sorted(
            [*actual_rows, *upcoming_rows],
            key=lambda row: (row["date"], 0 if row.get("is_planned") else 1),
            reverse=True,
        )
        prev_date: datetime.date | None = None
        for row in merged:
            row_date = datetime.date.fromisoformat(row["date"])
            row["sep_label"] = TransactionService.group_separator_label(
                row_date, prev_date, grouping, week_mode
            )
            prev_date = row_date
        return TransactionService.attach_group_nets(merged)

    @staticmethod
    def attach_group_nets(rows: builtins.list[dict[str, Any]]) -> builtins.list[dict[str, Any]]:
        """Give every separator row the net of the group it opens.

        Page-scoped on purpose: the rows handed in are the page the user is
        looking at, and summing anything else would mean a second query for a
        figure that sits inside the page's own scroll.
        """
        start: int | None = None
        for i, row in enumerate(rows):
            if not row.get("sep_label"):
                continue
            if start is not None:
                rows[start]["sep_net"] = TransactionService.group_net_label(rows[start:i])
            start = i
        if start is not None:
            rows[start]["sep_net"] = TransactionService.group_net_label(rows[start:])
        return rows

    @staticmethod
    def group_net_label(group: builtins.list[dict[str, Any]]) -> str:
        """A group's net as the separator shows it, or nothing at all.

        A week made entirely of upcoming planned rows has no net to show: none
        of that money has moved. Printing ``0.00`` there would claim the week
        came out even, which is a different statement from "nothing is
        recorded yet". A group that holds only transfers still reads ``0.00``,
        because in that case nothing really did leave the user.
        """
        if group and all(row.get("is_planned") for row in group):
            return ""
        return TransactionService.format_net(TransactionService.net_of_rows(group))

    @staticmethod
    def net_of_rows(rows: builtins.list[dict[str, Any]]) -> Decimal:
        """What a set of ledger rows did to the user's money.

        Transfers are left out of it entirely. The money only moved between
        the user's own accounts, so it neither entered nor left: counting both
        legs would show money leaving once and arriving once (or, on a single
        selected account, leaving twice), and counting a lone leg would claim
        a direction the net has no business claiming. A net that says nothing
        about a transfer is honest, and the rule is the same wherever it is
        read, so the group separator and the selection bar cannot disagree.
        (Each leg's own figure is signed by its ``transfer_direction`` for the
        column — see ``signed_amount`` — but that sign never reaches here.)

        An upcoming planned row is left out for the same reason: the money has
        not moved yet, and a net that mixed a forecast into a record of the
        past would be neither.
        """
        return sum(
            (
                # ``or 0`` and not a ``get`` default: a separator row carries
                # no figure at all, and a row can carry an explicit ``None``.
                # ``Decimal("None")`` would raise and take the whole bar down.
                Decimal(str(row.get("amount_value") or 0))
                for row in rows
                if row.get("type") != TransactionType.TRANSFER.value and not row.get("is_planned")
            ),
            Decimal("0"),
        )
