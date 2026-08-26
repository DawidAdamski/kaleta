# SPDX-License-Identifier: AGPL-3.0-or-later
"""Money-flow Sankey graph builder — budget or account lens."""

from __future__ import annotations

import datetime
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from kaleta.models.account import Account
from kaleta.models.category import Category
from kaleta.models.transaction import Transaction, TransactionType
from kaleta.services.categorised_flows import categorised_flows_selectable

NodeKind = Literal["source", "pool", "sink", "surplus", "deficit", "account"]
FlowMode = Literal["budget", "accounts"]

POOL_ID = "pool"
SURPLUS_ID = "surplus"
DEFICIT_ID = "deficit"
IN_OTHER_ID = "in:other"
OUT_OTHER_ID = "out:other"
IN_UNCATEGORISED_ID = "in:uncategorised"
OUT_UNCATEGORISED_ID = "out:uncategorised"


@dataclass(frozen=True)
class MoneyFlowLabels:
    """Display labels for structural nodes (view passes i18n)."""

    pool: str = "Budget"
    surplus: str = "Surplus"
    deficit: str = "Covered from savings"
    other: str = "Other"
    uncategorised: str = "Uncategorised"
    income_suffix: str = "income"
    expense_suffix: str = "expense"


@dataclass
class MoneyFlowNode:
    id: str
    label: str
    kind: NodeKind


@dataclass
class MoneyFlowLink:
    source: str
    target: str
    amount: Decimal


@dataclass
class MoneyFlow:
    nodes: list[MoneyFlowNode] = field(default_factory=list)
    links: list[MoneyFlowLink] = field(default_factory=list)
    total_in: Decimal = Decimal("0")
    total_out: Decimal = Decimal("0")
    net: Decimal = Decimal("0")
    total_transfers: Decimal = Decimal("0")
    period_label: str = ""
    mode: FlowMode = "budget"


@dataclass
class _Bucket:
    node_id: str
    label: str
    amount: Decimal
    parent_id: str | None = None
    parent_label: str | None = None


@dataclass(frozen=True)
class _FlowRow:
    category_id: int | None
    name: str | None
    parent_id: int | None
    parent_name: str | None
    type: TransactionType
    total: Decimal
    account_id: int | None = None
    account_name: str | None = None


@dataclass(frozen=True)
class _TransferEdge:
    from_account_id: int
    from_account_name: str
    to_account_id: int
    to_account_name: str
    amount: Decimal


class MoneyFlowService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def build(
        self,
        start: datetime.date,
        end: datetime.date,
        *,
        top_n: int | None = 12,
        depth: int = 1,
        mode: FlowMode = "budget",
        labels: MoneyFlowLabels | None = None,
    ) -> MoneyFlow:
        """Build a Sankey for ``[start, end)``.

        ``mode="budget"`` — income → Budget pool → expenses.
        ``mode="accounts"`` — income → accounts → expenses, plus net transfers.
        """
        lbl = labels or MoneyFlowLabels()
        depth = 1 if depth < 1 else (2 if depth > 2 else depth)
        mode = "accounts" if mode == "accounts" else "budget"
        if mode == "accounts":
            return await self._build_accounts(start, end, top_n=top_n, depth=depth, labels=lbl)
        return await self._build_budget(start, end, top_n=top_n, depth=depth, labels=lbl)

    async def _build_budget(
        self,
        start: datetime.date,
        end: datetime.date,
        *,
        top_n: int | None,
        depth: int,
        labels: MoneyFlowLabels,
    ) -> MoneyFlow:
        period_label = _period_label(start, end)
        rows = await self._sum_by_category(start, end, by_account=False)
        if not rows:
            return MoneyFlow(period_label=period_label, mode="budget")

        income_buckets = self._income_buckets(rows, depth, labels)
        expense_buckets = self._expense_buckets(rows, depth, labels)
        income_buckets = _fold(income_buckets, top_n, IN_OTHER_ID, labels.other)
        expense_buckets = _fold(expense_buckets, top_n, OUT_OTHER_ID, labels.other)

        total_in = sum((b.amount for b in income_buckets), start=Decimal("0"))
        total_out = sum((b.amount for b in expense_buckets), start=Decimal("0"))
        if total_in == 0 and total_out == 0:
            return MoneyFlow(period_label=period_label, mode="budget")

        net = total_in - total_out
        nodes: dict[str, MoneyFlowNode] = {
            POOL_ID: MoneyFlowNode(id=POOL_ID, label=labels.pool, kind="pool"),
        }
        links: list[MoneyFlowLink] = []

        for bucket in income_buckets:
            nodes[bucket.node_id] = MoneyFlowNode(
                id=bucket.node_id, label=bucket.label, kind="source"
            )
            links.append(MoneyFlowLink(bucket.node_id, POOL_ID, bucket.amount))

        if net < 0:
            nodes[DEFICIT_ID] = MoneyFlowNode(id=DEFICIT_ID, label=labels.deficit, kind="deficit")
            links.append(MoneyFlowLink(DEFICIT_ID, POOL_ID, -net))

        for bucket in expense_buckets:
            if depth == 2 and bucket.parent_id and bucket.parent_label:
                parent_id = bucket.parent_id
                if parent_id not in nodes:
                    nodes[parent_id] = MoneyFlowNode(
                        id=parent_id, label=bucket.parent_label, kind="sink"
                    )
                links.append(MoneyFlowLink(POOL_ID, parent_id, bucket.amount))
                nodes[bucket.node_id] = MoneyFlowNode(
                    id=bucket.node_id, label=bucket.label, kind="sink"
                )
                links.append(MoneyFlowLink(parent_id, bucket.node_id, bucket.amount))
            else:
                nodes[bucket.node_id] = MoneyFlowNode(
                    id=bucket.node_id, label=bucket.label, kind="sink"
                )
                links.append(MoneyFlowLink(POOL_ID, bucket.node_id, bucket.amount))

        if net > 0:
            nodes[SURPLUS_ID] = MoneyFlowNode(id=SURPLUS_ID, label=labels.surplus, kind="surplus")
            links.append(MoneyFlowLink(POOL_ID, SURPLUS_ID, net))

        _disambiguate_labels(nodes, labels)
        return MoneyFlow(
            nodes=list(nodes.values()),
            links=_merge_links(links),
            total_in=total_in,
            total_out=total_out,
            net=net,
            period_label=period_label,
            mode="budget",
        )

    async def _build_accounts(
        self,
        start: datetime.date,
        end: datetime.date,
        *,
        top_n: int | None,
        depth: int,
        labels: MoneyFlowLabels,
    ) -> MoneyFlow:
        period_label = _period_label(start, end)
        rows = await self._sum_by_category(start, end, by_account=True)
        transfer_edges = await self._net_transfers(start, end)
        if not rows and not transfer_edges:
            return MoneyFlow(period_label=period_label, mode="accounts")

        # Fold categories globally, then attribute per-account edges to kept/other.
        income_totals = self._income_buckets(rows, depth, labels)
        expense_totals = self._expense_buckets(rows, depth, labels)
        income_kept = {b.node_id for b in _fold(income_totals, top_n, IN_OTHER_ID, labels.other)}
        expense_kept = {b.node_id for b in _fold(expense_totals, top_n, OUT_OTHER_ID, labels.other)}

        nodes: dict[str, MoneyFlowNode] = {}
        links: list[MoneyFlowLink] = []
        total_in = Decimal("0")
        total_out = Decimal("0")

        for row in rows:
            if row.account_id is None or row.account_name is None:
                continue
            amount = row.total
            if amount == 0:
                continue
            acc_id = f"acc:{row.account_id}"
            if acc_id not in nodes:
                nodes[acc_id] = MoneyFlowNode(
                    id=acc_id, label=str(row.account_name), kind="account"
                )

            if row.type == TransactionType.INCOME:
                cat_id, cat_label = _category_node(row, depth, labels, side="in")
                if cat_id not in income_kept:
                    cat_id, cat_label = IN_OTHER_ID, labels.other
                if cat_id not in nodes:
                    nodes[cat_id] = MoneyFlowNode(id=cat_id, label=cat_label, kind="source")
                links.append(MoneyFlowLink(cat_id, acc_id, amount))
                total_in += amount
            elif row.type == TransactionType.EXPENSE:
                cat_id, cat_label, parent_id, parent_label = _expense_category_node(
                    row, depth, labels
                )
                if cat_id not in expense_kept:
                    cat_id, cat_label = OUT_OTHER_ID, labels.other
                    parent_id = parent_label = None
                if depth == 2 and parent_id and parent_label and cat_id != OUT_OTHER_ID:
                    if parent_id not in nodes:
                        nodes[parent_id] = MoneyFlowNode(
                            id=parent_id, label=parent_label, kind="sink"
                        )
                    links.append(MoneyFlowLink(acc_id, parent_id, amount))
                    if cat_id not in nodes:
                        nodes[cat_id] = MoneyFlowNode(id=cat_id, label=cat_label, kind="sink")
                    links.append(MoneyFlowLink(parent_id, cat_id, amount))
                else:
                    if cat_id not in nodes:
                        nodes[cat_id] = MoneyFlowNode(id=cat_id, label=cat_label, kind="sink")
                    links.append(MoneyFlowLink(acc_id, cat_id, amount))
                total_out += amount

        total_transfers = Decimal("0")
        for edge in transfer_edges:
            src_id = f"acc:{edge.from_account_id}"
            dst_id = f"acc:{edge.to_account_id}"
            if src_id not in nodes:
                nodes[src_id] = MoneyFlowNode(
                    id=src_id, label=edge.from_account_name, kind="account"
                )
            if dst_id not in nodes:
                nodes[dst_id] = MoneyFlowNode(id=dst_id, label=edge.to_account_name, kind="account")
            links.append(MoneyFlowLink(src_id, dst_id, edge.amount))
            total_transfers += edge.amount

        _disambiguate_labels(nodes, labels)
        return MoneyFlow(
            nodes=list(nodes.values()),
            links=_merge_links(links),
            total_in=total_in,
            total_out=total_out,
            net=total_in - total_out,
            total_transfers=total_transfers,
            period_label=period_label,
            mode="accounts",
        )

    async def _sum_by_category(
        self, start: datetime.date, end: datetime.date, *, by_account: bool
    ) -> list[_FlowRow]:
        flow = categorised_flows_selectable()
        parent = aliased(Category)
        cols: list[Any] = [
            flow.c.category_id.label("category_id"),
            Category.name.label("name"),
            Category.parent_id.label("parent_id"),
            parent.name.label("parent_name"),
            flow.c.type.label("type"),
            func.sum(flow.c.amount).label("total"),
        ]
        group_by: list[Any] = [
            flow.c.category_id,
            Category.name,
            Category.parent_id,
            parent.name,
            flow.c.type,
        ]
        if by_account:
            cols.extend(
                [
                    flow.c.account_id.label("account_id"),
                    Account.name.label("account_name"),
                ]
            )
            group_by.extend([flow.c.account_id, Account.name])

        stmt = (
            select(*cols)
            .select_from(flow)
            .join(Category, flow.c.category_id == Category.id, isouter=True)
            .join(parent, Category.parent_id == parent.id, isouter=True)
            .where(
                flow.c.date >= start,
                flow.c.date < end,
                flow.c.is_internal_transfer == False,  # noqa: E712
                flow.c.type.in_([TransactionType.INCOME, TransactionType.EXPENSE]),
            )
            .group_by(*group_by)
        )
        if by_account:
            stmt = stmt.join(Account, flow.c.account_id == Account.id)

        result = await self.session.execute(stmt)
        return [
            _FlowRow(
                category_id=row.category_id,
                name=row.name,
                parent_id=row.parent_id,
                parent_name=row.parent_name,
                type=row.type,
                total=Decimal(str(row.total)),
                account_id=getattr(row, "account_id", None),
                account_name=getattr(row, "account_name", None),
            )
            for row in result.all()
        ]

    async def _net_transfers(self, start: datetime.date, end: datetime.date) -> list[_TransferEdge]:
        """Net paired internal transfers into an acyclic account→account edge list."""
        src = aliased(Transaction)
        dst = aliased(Transaction)
        src_acc = aliased(Account)
        dst_acc = aliased(Account)
        stmt = (
            select(
                src.account_id.label("from_id"),
                src_acc.name.label("from_name"),
                dst.account_id.label("to_id"),
                dst_acc.name.label("to_name"),
                src.amount.label("amount"),
            )
            .select_from(src)
            .join(dst, src.linked_transaction_id == dst.id)
            .join(src_acc, src.account_id == src_acc.id)
            .join(dst_acc, dst.account_id == dst_acc.id)
            .where(
                src.is_internal_transfer == True,  # noqa: E712
                src.type == TransactionType.TRANSFER,
                src.linked_transaction_id.is_not(None),
                src.id < dst.id,
                src.account_id != dst.account_id,
                and_(src.date >= start, src.date < end),
            )
        )
        result = await self.session.execute(stmt)
        raw: dict[tuple[int, int], tuple[str, str, Decimal]] = {}
        for row in result.all():
            key = (int(row.from_id), int(row.to_id))
            amount = Decimal(str(row.amount))
            if key in raw:
                prev_from, prev_to, prev_amt = raw[key]
                raw[key] = (prev_from, prev_to, prev_amt + amount)
            else:
                raw[key] = (str(row.from_name), str(row.to_name), amount)

        netted: dict[tuple[int, int], tuple[str, str, Decimal]] = {}
        seen: set[tuple[int, int]] = set()
        for (a, b), (a_name, b_name, amt) in raw.items():
            if (a, b) in seen:
                continue
            rev = (b, a)
            if rev in raw:
                rev_a_name, rev_b_name, rev_amt = raw[rev]
                seen.add(rev)
                if amt >= rev_amt:
                    diff = amt - rev_amt
                    if diff > 0:
                        netted[(a, b)] = (a_name, b_name, diff)
                else:
                    diff = rev_amt - amt
                    if diff > 0:
                        netted[(b, a)] = (rev_a_name, rev_b_name, diff)
            else:
                netted[(a, b)] = (a_name, b_name, amt)
            seen.add((a, b))

        return [
            _TransferEdge(
                from_account_id=a,
                from_account_name=a_name,
                to_account_id=b,
                to_account_name=b_name,
                amount=amt,
            )
            for (a, b), (a_name, b_name, amt) in netted.items()
        ]

    def _income_buckets(
        self, rows: list[_FlowRow], depth: int, lbl: MoneyFlowLabels
    ) -> list[_Bucket]:
        _ = depth
        merged: dict[str, _Bucket] = {}
        for row in rows:
            if row.type != TransactionType.INCOME:
                continue
            amount = row.total
            if amount == 0:
                continue
            node_id, label = _category_node(row, depth, lbl, side="in")
            existing = merged.get(node_id)
            if existing is None:
                merged[node_id] = _Bucket(node_id, label, amount)
            else:
                existing.amount += amount
        return list(merged.values())

    def _expense_buckets(
        self, rows: list[_FlowRow], depth: int, lbl: MoneyFlowLabels
    ) -> list[_Bucket]:
        merged: dict[str, _Bucket] = {}
        for row in rows:
            if row.type != TransactionType.EXPENSE:
                continue
            amount = row.total
            if amount == 0:
                continue
            node_id, label, parent_id, parent_label = _expense_category_node(row, depth, lbl)
            existing = merged.get(node_id)
            if existing is None:
                merged[node_id] = _Bucket(
                    node_id, label, amount, parent_id=parent_id, parent_label=parent_label
                )
            else:
                existing.amount += amount
        return list(merged.values())


def _category_node(
    row: _FlowRow, depth: int, lbl: MoneyFlowLabels, *, side: Literal["in", "out"]
) -> tuple[str, str]:
    _ = depth
    prefix = "in" if side == "in" else "out"
    if row.category_id is None:
        return (
            IN_UNCATEGORISED_ID if side == "in" else OUT_UNCATEGORISED_ID,
            lbl.uncategorised,
        )
    if side == "in" and row.parent_id is not None:
        return f"{prefix}:{row.parent_id}", str(row.parent_name)
    if side == "out" and depth == 1 and row.parent_id is not None:
        return f"{prefix}:{row.parent_id}", str(row.parent_name)
    return f"{prefix}:{row.category_id}", str(row.name)


def _expense_category_node(
    row: _FlowRow, depth: int, lbl: MoneyFlowLabels
) -> tuple[str, str, str | None, str | None]:
    if row.category_id is None:
        return OUT_UNCATEGORISED_ID, lbl.uncategorised, None, None
    if depth == 2 and row.parent_id is not None:
        return (
            f"out:{row.category_id}",
            str(row.name),
            f"out:{row.parent_id}",
            str(row.parent_name),
        )
    if depth == 1 and row.parent_id is not None:
        return f"out:{row.parent_id}", str(row.parent_name), None, None
    return f"out:{row.category_id}", str(row.name), None, None


def _disambiguate_labels(nodes: dict[str, MoneyFlowNode], lbl: MoneyFlowLabels) -> None:
    """Ensure display labels are unique — ECharts uses ``name`` as identity."""
    counts = Counter(n.label for n in nodes.values())
    if all(c == 1 for c in counts.values()):
        return
    for node in nodes.values():
        if counts[node.label] <= 1:
            continue
        if node.kind == "source":
            node.label = f"{node.label} ({lbl.income_suffix})"
        elif node.kind == "sink":
            node.label = f"{node.label} ({lbl.expense_suffix})"
        elif node.kind == "account":
            node.label = f"{node.label} [{node.id.removeprefix('acc:')}]"


def _fold(
    buckets: list[_Bucket], top_n: int | None, other_id: str, other_label: str
) -> list[_Bucket]:
    ordered = sorted(buckets, key=lambda b: b.amount, reverse=True)
    if top_n is None or len(ordered) <= top_n:
        return ordered
    keep = ordered[:top_n]
    rest_sum = sum((b.amount for b in ordered[top_n:]), start=Decimal("0"))
    if rest_sum > 0:
        keep.append(_Bucket(other_id, other_label, rest_sum))
    return keep


def _merge_links(links: list[MoneyFlowLink]) -> list[MoneyFlowLink]:
    merged: dict[tuple[str, str], Decimal] = {}
    for link in links:
        key = (link.source, link.target)
        merged[key] = merged.get(key, Decimal("0")) + link.amount
    return [
        MoneyFlowLink(source=s, target=t, amount=amt) for (s, t), amt in merged.items() if amt > 0
    ]


def _period_label(start: datetime.date, end: datetime.date) -> str:
    """Human label for a half-open ``[start, end)`` window."""
    last = end - datetime.timedelta(days=1)
    if start.day == 1 and end == _next_month(start):
        return f"{start.year}-{start.month:02d}"
    if start.month == 1 and start.day == 1 and end == datetime.date(start.year + 1, 1, 1):
        return str(start.year)
    if start == last:
        return start.isoformat()
    return f"{start.isoformat()} – {last.isoformat()}"


def _next_month(d: datetime.date) -> datetime.date:
    if d.month == 12:
        return datetime.date(d.year + 1, 1, 1)
    return datetime.date(d.year, d.month + 1, 1)


def month_bounds(year: int, month: int) -> tuple[datetime.date, datetime.date]:
    start = datetime.date(year, month, 1)
    return start, _next_month(start)


def year_bounds(year: int) -> tuple[datetime.date, datetime.date]:
    return datetime.date(year, 1, 1), datetime.date(year + 1, 1, 1)


def inclusive_end_exclusive(end_inclusive: datetime.date) -> datetime.date:
    """Convert an inclusive UI/API end date to half-open exclusive end."""
    return end_inclusive + datetime.timedelta(days=1)
