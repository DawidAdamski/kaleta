# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import builtins
import datetime
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.db.sql_compat import date_weekday, date_year, date_year_month
from kaleta.exceptions import ValidationError
from kaleta.models.account import Account
from kaleta.models.category import Category
from kaleta.models.institution import Institution
from kaleta.models.report import SavedReport
from kaleta.models.transaction import Transaction, TransactionType
from kaleta.schemas.report import SavedReportCreate
from kaleta.services.categorised_flows import categorised_flows_selectable

# ── Config dataclass ───────────────────────────────────────────────────────────

Dimension = Literal["category", "account", "month", "year", "type", "institution", "weekday"]
Metric = Literal["sum", "count", "avg"]
ChartType = Literal["pie", "donut", "bar", "line", "table"]
DatePreset = Literal[
    "all_time",
    "this_month",
    "last_month",
    "this_year",
    "last_year",
    "last_30",
    "last_90",
    "last_12_months",
    "custom",
]

_WEEKDAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

#: The dimensions that are a sequence rather than a bucket. They are ordered
#: chronologically on either axis of a pivot, where everything else is
#: ordered by what it adds up to.
TIME_DIMENSIONS: frozenset[str] = frozenset({"month", "year", "weekday"})

#: What the rows cut off by ``top_n`` are folded into on a pivot. A column
#: total that counted rows the table does not draw would read as a bug, and
#: one that ignored them would disagree with the ledger.
OTHER_ROW_LABEL = "Other"


@dataclass
class ReportConfig:
    dimension: Dimension = "category"
    #: The second axis, or ``None`` for the one-dimensional report that
    #: every saved report was before it existed.
    series: Dimension | None = None
    metric: Metric = "sum"
    chart_type: ChartType = "bar"
    transaction_types: list[str] = field(default_factory=lambda: ["expense"])
    date_preset: DatePreset = "this_year"
    date_from: str | None = None  # ISO date string
    date_to: str | None = None  # ISO date string
    account_ids: list[int] = field(default_factory=list)
    category_ids: list[int] = field(default_factory=list)
    top_n: int | None = 10

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "series": self.series,
            "metric": self.metric,
            "chart_type": self.chart_type,
            "transaction_types": self.transaction_types,
            "date_preset": self.date_preset,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "account_ids": self.account_ids,
            "category_ids": self.category_ids,
            "top_n": self.top_n,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ReportConfig:
        return cls(
            dimension=d.get("dimension", "category"),
            series=d.get("series"),
            metric=d.get("metric", "sum"),
            chart_type=d.get("chart_type", "bar"),
            transaction_types=d.get("transaction_types", ["expense"]),
            date_preset=d.get("date_preset", "this_year"),
            date_from=d.get("date_from"),
            date_to=d.get("date_to"),
            account_ids=d.get("account_ids", []),
            category_ids=d.get("category_ids", []),
            top_n=d.get("top_n", 10),
        )


@dataclass
class ReportResult:
    labels: list[str]
    values: list[float]
    column_header: str  # e.g. "Category", "Month"
    metric_header: str  # e.g. "Total Amount", "Count"


@dataclass(frozen=True)
class PivotResult:
    """A report grouped by two dimensions: rows, series, and a cell for each pair.

    ``cells[row][series]`` is the metric for that pair, zero where the
    ledger has nothing — a category with no spend in March is a zero in
    March, not a missing column. The totals are sums along each axis, which
    is arithmetic the ``avg`` metric has no use for: a column of averages
    added together is not the average of anything (`KAL-RPT-004`), and the
    view leaves the Total column and footer off on that measure.
    """

    row_header: str  # e.g. "Category"
    series_header: str  # e.g. "Month"
    row_labels: list[str]
    series_labels: list[str]
    cells: list[list[float]]  # [row][series]
    metric_header: str
    row_totals: list[float]
    series_totals: list[float]


@dataclass(frozen=True)
class ReportTableData:
    columns: list[dict[str, str]]
    rows: list[dict[str, str]]


_CHART_TYPE_ICONS: dict[str, str] = {
    "bar": "bar_chart",
    "line": "show_chart",
    "pie": "pie_chart",
    "donut": "donut_large",
    "table": "table_chart",
}


def chart_type_icon(chart_type: str) -> str:
    return _CHART_TYPE_ICONS.get(chart_type, "bar_chart")


def report_config_from_builder_state(state: dict[str, Any]) -> ReportConfig:
    """Build a ``ReportConfig`` from the report builder UI state dict."""
    return ReportConfig(
        dimension=state["dimension"],
        series=state["series"],
        metric=state["metric"],
        chart_type=state["chart_type"],
        transaction_types=state["transaction_types"],
        date_preset=state["date_preset"],
        date_from=state["date_from"] or None,
        date_to=state["date_to"] or None,
        account_ids=state["account_ids"],
        category_ids=state["category_ids"],
        top_n=int(state["top_n"] or 0) or None,
    )


def build_report_table_data(result: ReportResult) -> ReportTableData:
    columns = [
        {
            "name": "label",
            "label": result.column_header,
            "field": "label",
            "align": "left",
        },
        {
            "name": "value",
            "label": result.metric_header,
            "field": "value",
            "align": "right",
        },
    ]
    rows = [
        {"label": lbl, "value": f"{v:,.2f}"}
        for lbl, v in zip(result.labels, result.values, strict=False)
    ]
    return ReportTableData(columns=columns, rows=rows)


# ── Service ────────────────────────────────────────────────────────────────────


class SavedReportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── CRUD ──────────────────────────────────────────────────────────────────

    async def list(self) -> builtins.list[SavedReport]:
        result = await self.session.execute(select(SavedReport).order_by(SavedReport.name))
        return builtins.list(result.scalars().all())

    async def get(self, report_id: int) -> SavedReport | None:
        result = await self.session.execute(select(SavedReport).where(SavedReport.id == report_id))
        return result.scalar_one_or_none()

    async def create(self, data: SavedReportCreate) -> SavedReport:
        report = SavedReport(name=data.name, config=data.config)
        self.session.add(report)
        await self.session.commit()
        await self.session.refresh(report)
        return report

    async def delete(self, report_id: int) -> None:
        report = await self.get(report_id)
        if report:
            await self.session.delete(report)
            await self.session.commit()

    # ── Query execution ────────────────────────────────────────────────────────

    async def execute(self, config: ReportConfig) -> ReportResult | PivotResult:
        """Run the query. A ``series`` makes the answer a matrix, not a list.

        Callers branch on the type they get back: a report without a second
        dimension is the ``ReportResult`` it has always been, so every saved
        report still runs and draws exactly as it did.
        """
        if config.series is not None and config.series == config.dimension:
            raise ValidationError("A report cannot be grouped by the same dimension twice.")
        date_from, date_to = self._resolve_dates(config)
        # The flows path attributes split lines to their own categories, so it
        # is the one that can answer for a category on *either* axis.
        if config.dimension == "category" or config.series == "category" or config.category_ids:
            return await self._execute_on_flows(config, date_from, date_to)
        return await self._execute_on_transactions(config, date_from, date_to)

    async def _execute_on_transactions(
        self,
        config: ReportConfig,
        date_from: datetime.date | None,
        date_to: datetime.date | None,
    ) -> ReportResult | PivotResult:
        filters = self._transaction_filters(config, date_from, date_to)
        dim_expr, joins, col_header, is_weekday = self._dimension(config.dimension)
        metric_expr, metric_header = self._metric_exprs(config.metric, use_flows=False)

        if config.series is not None:
            series_expr, series_joins, series_header, series_is_weekday = self._dimension(
                config.series
            )
            stmt = (
                select(
                    dim_expr.label("label"),
                    series_expr.label("series"),
                    metric_expr.label("value"),
                )
                .where(*filters)
                .group_by(dim_expr, series_expr)
            )
            for join_target, condition, isouter in self._merge_joins(joins, series_joins):
                stmt = stmt.join(join_target, condition, isouter=isouter)
            rows = builtins.list((await self.session.execute(stmt)).fetchall())
            return self._rows_to_pivot(
                rows,
                config=config,
                headers=(col_header, series_header, metric_header),
                weekday_axes=(is_weekday, series_is_weekday),
            )

        stmt = (
            select(dim_expr.label("label"), metric_expr.label("value"))
            .where(*filters)
            .group_by(dim_expr)
            .order_by(metric_expr.desc())
        )
        for join_target, condition, isouter in joins:
            stmt = stmt.join(join_target, condition, isouter=isouter)
        if config.top_n and config.top_n > 0:
            stmt = stmt.limit(config.top_n)

        rows = builtins.list((await self.session.execute(stmt)).fetchall())
        return self._rows_to_result(rows, col_header, metric_header, is_weekday)

    async def _execute_on_flows(
        self,
        config: ReportConfig,
        date_from: datetime.date | None,
        date_to: datetime.date | None,
    ) -> ReportResult | PivotResult:
        flow = categorised_flows_selectable()
        filters = self._flow_filters(config, date_from, date_to, flow)
        dim_expr, joins, col_header, is_weekday = self._flow_dimension(config.dimension, flow)
        metric_expr, metric_header = self._metric_exprs(config.metric, use_flows=True, flow=flow)

        if config.series is not None:
            series_expr, series_joins, series_header, series_is_weekday = self._flow_dimension(
                config.series, flow
            )
            stmt = (
                select(
                    dim_expr.label("label"),
                    series_expr.label("series"),
                    metric_expr.label("value"),
                )
                .select_from(flow)
                .where(*filters)
                .group_by(dim_expr, series_expr)
            )
            for join_target, condition, isouter in self._merge_joins(joins, series_joins):
                stmt = stmt.join(join_target, condition, isouter=isouter)
            rows = builtins.list((await self.session.execute(stmt)).fetchall())
            return self._rows_to_pivot(
                rows,
                config=config,
                headers=(col_header, series_header, metric_header),
                weekday_axes=(is_weekday, series_is_weekday),
            )

        stmt = (
            select(dim_expr.label("label"), metric_expr.label("value"))
            .select_from(flow)
            .where(*filters)
            .group_by(dim_expr)
            .order_by(metric_expr.desc())
        )
        for join_target, condition, isouter in joins:
            stmt = stmt.join(join_target, condition, isouter=isouter)
        if config.top_n and config.top_n > 0:
            stmt = stmt.limit(config.top_n)

        rows = builtins.list((await self.session.execute(stmt)).fetchall())
        return self._rows_to_result(rows, col_header, metric_header, is_weekday)

    @staticmethod
    def _merge_joins(
        *join_lists: builtins.list[tuple[Any, Any, bool]],
    ) -> builtins.list[tuple[Any, Any, bool]]:
        """Both axes' joins, each table joined once.

        Grouping by Institution and Account both want ``accounts`` in the
        statement, and joining it twice is an error rather than a wider query.
        The first condition for a table wins: the axes ask for the same rows,
        so the two conditions on a shared table are the same condition.
        """
        merged: builtins.list[tuple[Any, Any, bool]] = []
        seen: set[Any] = set()
        for joins in join_lists:
            for join_target, condition, isouter in joins:
                if join_target in seen:
                    continue
                seen.add(join_target)
                merged.append((join_target, condition, isouter))
        return merged

    # ── Pivot shaping ─────────────────────────────────────────────────────────

    @classmethod
    def _rows_to_pivot(
        cls,
        rows: builtins.list[Any],
        *,
        config: ReportConfig,
        headers: tuple[str, str, str],
        weekday_axes: tuple[bool, bool],
    ) -> PivotResult:
        """Turn ``(row, series, value)`` triples into the matrix the view draws.

        Ordering and the ``top_n`` cut happen here rather than in SQL: the row
        axis is cut by what each row *totals* across the whole series, which is
        a figure the grouped query does not have a row for.
        """
        row_header, series_header, metric_header = headers
        row_is_weekday, series_is_weekday = weekday_axes
        assert config.series is not None  # only ever called on the pivot path

        cells: dict[Any, dict[Any, float]] = {}
        row_totals: dict[Any, float] = {}
        for row in rows:
            value = float(row.value) if row.value is not None else 0.0
            cells.setdefault(row.label, {})[row.series] = value
            row_totals[row.label] = row_totals.get(row.label, 0.0) + value

        series_totals: dict[Any, float] = {}
        for by_series in cells.values():
            for series_key, value in by_series.items():
                series_totals[series_key] = series_totals.get(series_key, 0.0) + value

        kept, folded = cls._cut_rows(row_totals, config)
        row_order = cls._axis_order(kept, config.dimension, row_totals)
        series_order = cls._axis_order(builtins.list(series_totals), config.series, series_totals)

        matrix = [[cells.get(key, {}).get(s, 0.0) for s in series_order] for key in row_order]
        labels = [cls._label_of(key, row_is_weekday) for key in row_order]
        if folded:
            matrix.append(
                [sum(cells.get(key, {}).get(s, 0.0) for key in folded) for s in series_order]
            )
            labels.append(OTHER_ROW_LABEL)

        return PivotResult(
            row_header=row_header,
            series_header=series_header,
            row_labels=labels,
            series_labels=[cls._label_of(key, series_is_weekday) for key in series_order],
            cells=matrix,
            metric_header=metric_header,
            row_totals=[sum(cell_row) for cell_row in matrix],
            series_totals=[sum(column) for column in zip(*matrix, strict=True)] if matrix else [],
        )

    @staticmethod
    def _cut_rows(
        row_totals: dict[Any, float],
        config: ReportConfig,
    ) -> tuple[builtins.list[Any], builtins.list[Any]]:
        """The rows the pivot draws, and the ones an ``Other`` row stands for.

        ``top_n`` keeps the biggest rows by their total across the series, not
        the first ones on the axis: a pivot of twelve months cut to the ten
        earliest would answer a question nobody asked.

        Nothing is folded on the ``avg`` measure — averaging a column of
        averages is the same lie as summing one (`KAL-RPT-004`), so the
        cut-off rows are left out instead of being misrepresented.
        """
        keys = builtins.list(row_totals)
        limit = config.top_n or 0
        if limit <= 0 or len(keys) <= limit:
            return keys, []
        biggest = sorted(keys, key=lambda key: row_totals[key], reverse=True)
        if config.metric == "avg":
            return biggest[:limit], []
        return biggest[:limit], biggest[limit:]

    @staticmethod
    def _axis_order(
        keys: builtins.list[Any],
        dimension: Dimension,
        totals: dict[Any, float],
    ) -> builtins.list[Any]:
        """A sequence stays in its own order; a bucket is ranked by its total.

        Sorted on the raw grouped value rather than on the label, so weekdays
        run Sunday-first off their index instead of alphabetically off their
        name.
        """
        if dimension in TIME_DIMENSIONS:
            return sorted(keys, key=lambda key: (key is None, str(key)))
        return sorted(keys, key=lambda key: (-totals.get(key, 0.0), str(key)))

    @staticmethod
    def _label_of(raw: Any, is_weekday: bool) -> str:
        """The same labelling the one-dimensional path does, for one value."""
        if raw is None:
            return "?" if is_weekday else "—"
        return _WEEKDAY_NAMES[int(raw)] if is_weekday else str(raw)

    @staticmethod
    def _rows_to_result(
        rows: builtins.list[Any],
        col_header: str,
        metric_header: str,
        is_weekday: bool,
    ) -> ReportResult:
        if is_weekday:
            labels = [_WEEKDAY_NAMES[int(r.label)] if r.label is not None else "?" for r in rows]
        else:
            labels = [str(r.label) if r.label is not None else "—" for r in rows]

        values = [float(r.value) if r.value is not None else 0.0 for r in rows]
        return ReportResult(
            labels=labels,
            values=values,
            column_header=col_header,
            metric_header=metric_header,
        )

    @staticmethod
    def _transaction_filters(
        config: ReportConfig,
        date_from: datetime.date | None,
        date_to: datetime.date | None,
    ) -> builtins.list[Any]:
        filters: builtins.list[Any] = [Transaction.is_internal_transfer == False]  # noqa: E712
        if date_from:
            filters.append(Transaction.date >= date_from)
        if date_to:
            filters.append(Transaction.date <= date_to)
        filters.extend(SavedReportService._type_filters(config, Transaction.type))
        if config.account_ids:
            filters.append(Transaction.account_id.in_(config.account_ids))
        return filters

    @staticmethod
    def _flow_filters(
        config: ReportConfig,
        date_from: datetime.date | None,
        date_to: datetime.date | None,
        flow: Any,
    ) -> builtins.list[Any]:
        filters: builtins.list[Any] = [flow.c.is_internal_transfer == False]  # noqa: E712
        if date_from:
            filters.append(flow.c.date >= date_from)
        if date_to:
            filters.append(flow.c.date <= date_to)
        filters.extend(SavedReportService._type_filters(config, flow.c.type))
        if config.account_ids:
            filters.append(flow.c.account_id.in_(config.account_ids))
        if config.category_ids:
            filters.append(flow.c.category_id.in_(config.category_ids))
        return filters

    @staticmethod
    def _type_filters(config: ReportConfig, type_column: Any) -> builtins.list[Any]:
        if not config.transaction_types:
            return []
        _type_map = {
            "expense": TransactionType.EXPENSE,
            "income": TransactionType.INCOME,
            "transfer": TransactionType.TRANSFER,
        }
        type_clauses = [
            type_column == _type_map[t] for t in config.transaction_types if t in _type_map
        ]
        return [or_(*type_clauses)] if type_clauses else []

    @staticmethod
    def _metric_exprs(
        metric: Metric,
        *,
        use_flows: bool,
        flow: Any | None = None,
    ) -> tuple[Any, str]:
        amount_col = flow.c.amount if use_flows and flow is not None else Transaction.amount
        if metric == "sum":
            return func.sum(amount_col), "Total Amount"
        if metric == "count":
            if use_flows:
                return func.count(), "Count"
            return func.count(Transaction.id), "Count"
        return func.avg(amount_col), "Average"

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_dates(
        config: ReportConfig,
    ) -> tuple[datetime.date | None, datetime.date | None]:
        today = datetime.date.today()
        preset = config.date_preset

        if preset == "this_month":
            return today.replace(day=1), today
        if preset == "last_month":
            first = today.replace(day=1)
            last_day_prev = first - datetime.timedelta(days=1)
            return last_day_prev.replace(day=1), last_day_prev
        if preset == "this_year":
            return today.replace(month=1, day=1), today
        if preset == "last_year":
            y = today.year - 1
            return datetime.date(y, 1, 1), datetime.date(y, 12, 31)
        if preset == "last_30":
            return today - datetime.timedelta(days=30), today
        if preset == "last_90":
            return today - datetime.timedelta(days=90), today
        if preset == "last_12_months":
            return today - datetime.timedelta(days=365), today
        if preset == "custom":
            df = datetime.date.fromisoformat(config.date_from) if config.date_from else None
            dt = datetime.date.fromisoformat(config.date_to) if config.date_to else None
            return df, dt
        # all_time
        return None, None

    @staticmethod
    def _dimension(
        dim: Dimension,
    ) -> tuple[Any, builtins.list[tuple[Any, Any, bool]], str, bool]:
        """Return (dim_expr, joins, column_header, is_weekday)."""
        if dim == "category":
            return (
                func.coalesce(Category.name, "Uncategorised"),
                [(Category, Transaction.category_id == Category.id, True)],
                "Category",
                False,
            )
        if dim == "account":
            return (
                Account.name,
                [(Account, Transaction.account_id == Account.id, False)],
                "Account",
                False,
            )
        if dim == "institution":
            return (
                func.coalesce(Institution.name, "No Institution"),
                [
                    (Account, Transaction.account_id == Account.id, False),
                    (Institution, Account.institution_id == Institution.id, True),
                ],
                "Institution",
                False,
            )
        if dim == "month":
            return (
                date_year_month(Transaction.date),
                [],
                "Month",
                False,
            )
        if dim == "year":
            return (
                date_year(Transaction.date),
                [],
                "Year",
                False,
            )
        if dim == "type":
            return (
                Transaction.type,
                [],
                "Type",
                False,
            )
        if dim == "weekday":
            return (
                date_weekday(Transaction.date),
                [],
                "Weekday",
                True,
            )
        # fallback
        return (func.coalesce(Category.name, "Uncategorised"), [], "Category", False)

    @staticmethod
    def _flow_dimension(
        dim: Dimension,
        flow: Any,
    ) -> tuple[Any, builtins.list[tuple[Any, Any, bool]], str, bool]:
        """Return (dim_expr, joins, column_header, is_weekday) for categorised flows."""
        if dim == "category":
            return (
                func.coalesce(Category.name, "Uncategorised"),
                [(Category, flow.c.category_id == Category.id, True)],
                "Category",
                False,
            )
        if dim == "account":
            return (
                Account.name,
                [(Account, flow.c.account_id == Account.id, False)],
                "Account",
                False,
            )
        if dim == "institution":
            return (
                func.coalesce(Institution.name, "No Institution"),
                [
                    (Account, flow.c.account_id == Account.id, False),
                    (Institution, Account.institution_id == Institution.id, True),
                ],
                "Institution",
                False,
            )
        if dim == "month":
            return (
                date_year_month(flow.c.date),
                [],
                "Month",
                False,
            )
        if dim == "year":
            return (
                date_year(flow.c.date),
                [],
                "Year",
                False,
            )
        if dim == "type":
            return (
                flow.c.type,
                [],
                "Type",
                False,
            )
        if dim == "weekday":
            return (
                date_weekday(flow.c.date),
                [],
                "Weekday",
                True,
            )
        return (func.coalesce(Category.name, "Uncategorised"), [], "Category", False)
