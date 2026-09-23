# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for SavedReportService view helpers and query execution."""

from __future__ import annotations

import dataclasses
import datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import ValidationError
from kaleta.models.account import AccountType
from kaleta.models.category import CategoryType
from kaleta.models.transaction import TransactionType
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.category import CategoryCreate
from kaleta.schemas.transaction import TransactionCreate, TransactionSplitCreate
from kaleta.services import AccountService, CategoryService, SavedReportService, TransactionService
from kaleta.services.saved_report_service import (
    PivotResult,
    ReportConfig,
    ReportResult,
    build_report_table_data,
    chart_type_icon,
    report_config_from_builder_state,
)


class TestSavedReportViewHelpers:
    def test_chart_type_icon_defaults_to_bar(self) -> None:
        assert chart_type_icon("unknown") == "bar_chart"
        assert chart_type_icon("pie") == "pie_chart"

    def test_report_config_from_builder_state(self) -> None:
        state = {
            "dimension": "account",
            "series": None,
            "metric": "count",
            "chart_type": "line",
            "transaction_types": ["expense", "income"],
            "date_preset": "last_30",
            "date_from": "",
            "date_to": "",
            "account_ids": [1, 2],
            "category_ids": [],
            "top_n": 0,
        }
        config = report_config_from_builder_state(state)
        assert config.dimension == "account"
        assert config.series is None
        assert config.metric == "count"
        assert config.transaction_types == ["expense", "income"]
        assert config.top_n is None

    def test_build_report_table_data(self) -> None:
        result = ReportResult(
            labels=["Food", "Transport"],
            values=[100.5, 50.25],
            column_header="Category",
            metric_header="Total Amount",
        )
        table = build_report_table_data(result)
        assert len(table.columns) == 2
        assert table.rows[0]["label"] == "Food"
        assert table.rows[0]["value"] == "100.50"


@pytest.fixture
def report_svc(session: AsyncSession) -> SavedReportService:
    return SavedReportService(session)


async def _seed_split_lidl(
    session: AsyncSession,
) -> tuple[int, int, int]:
    acc = (
        await AccountService(session).create(
            AccountCreate(name="Checking", type=AccountType.CHECKING)
        )
    ).id
    groceries = (
        await CategoryService(session).create(
            CategoryCreate(name="Groceries", type=CategoryType.EXPENSE)
        )
    ).id
    alcohol = (
        await CategoryService(session).create(
            CategoryCreate(name="Alcohol", type=CategoryType.EXPENSE)
        )
    ).id
    await TransactionService(session).create(
        TransactionCreate(
            account_id=acc,
            amount=Decimal("214.50"),
            type=TransactionType.EXPENSE,
            date=datetime.date(2025, 6, 15),
            description="Lidl",
            is_split=True,
            splits=[
                TransactionSplitCreate(category_id=groceries, amount=Decimal("180.00")),
                TransactionSplitCreate(category_id=alcohol, amount=Decimal("34.50")),
            ],
        )
    )
    return groceries, alcohol, acc


class TestSplitAwareSavedReports:
    async def test_category_dimension_includes_split_lines(
        self, report_svc: SavedReportService, session: AsyncSession
    ):
        """Covers: KAL-SPL-003"""
        await _seed_split_lidl(session)
        result = await report_svc.execute(
            ReportConfig(
                dimension="category",
                metric="sum",
                transaction_types=["expense"],
                date_preset="custom",
                date_from="2025-06-01",
                date_to="2025-06-30",
            )
        )
        by_label = dict(zip(result.labels, result.values, strict=False))
        assert by_label["Groceries"] == pytest.approx(180.0)
        assert by_label["Alcohol"] == pytest.approx(34.5)

    async def test_category_filter_counts_only_matching_split_line(
        self, report_svc: SavedReportService, session: AsyncSession
    ):
        """Covers: KAL-SPL-003"""
        _, alcohol_id, _ = await _seed_split_lidl(session)
        result = await report_svc.execute(
            ReportConfig(
                dimension="category",
                metric="sum",
                transaction_types=["expense"],
                date_preset="custom",
                date_from="2025-06-01",
                date_to="2025-06-30",
                category_ids=[alcohol_id],
            )
        )
        assert result.labels == ["Alcohol"]
        assert result.values == [pytest.approx(34.5)]


async def _seed_two_months(session: AsyncSession) -> tuple[int, int]:
    """Food in January and February, Fun only in February.

    The hole is the point: a pivot must draw Fun's January as a zero rather
    than as a missing cell.
    """
    account = (
        await AccountService(session).create(
            AccountCreate(name="Checking", type=AccountType.CHECKING)
        )
    ).id
    food = (
        await CategoryService(session).create(
            CategoryCreate(name="Food", type=CategoryType.EXPENSE)
        )
    ).id
    fun = (
        await CategoryService(session).create(CategoryCreate(name="Fun", type=CategoryType.EXPENSE))
    ).id
    for category_id, amount, day in (
        (food, "100.00", datetime.date(2025, 1, 10)),
        (food, "50.00", datetime.date(2025, 2, 10)),
        (fun, "30.00", datetime.date(2025, 2, 15)),
    ):
        await TransactionService(session).create(
            TransactionCreate(
                account_id=account,
                category_id=category_id,
                amount=Decimal(amount),
                type=TransactionType.EXPENSE,
                date=day,
                description="pivot fixture",
            )
        )
    return account, fun


def _pivot_config(**overrides: object) -> ReportConfig:
    """Category by Month over the two seeded months, with one field changed."""
    base = ReportConfig(
        dimension="category",
        series="month",
        metric="sum",
        transaction_types=["expense"],
        date_preset="custom",
        date_from="2025-01-01",
        date_to="2025-02-28",
    )
    return dataclasses.replace(base, **overrides)


class TestSecondDimensionConfig:
    def test_a_stored_config_without_a_series_stays_one_dimensional(self) -> None:
        # Every `saved_reports.config` written before the second dimension
        # existed has no "series" key, and must keep running as it did.
        assert ReportConfig.from_dict({"dimension": "category"}).series is None

    def test_the_series_round_trips_through_the_stored_json(self) -> None:
        config = ReportConfig(dimension="category", series="month")
        assert ReportConfig.from_dict(config.to_dict()).series == "month"


class TestPivotExecution:
    async def test_one_cell_per_pair_and_a_zero_where_the_ledger_is_empty(
        self, report_svc: SavedReportService, session: AsyncSession
    ):
        await _seed_two_months(session)
        result = await report_svc.execute(_pivot_config())
        assert isinstance(result, PivotResult)
        assert result.row_header == "Category"
        assert result.series_header == "Month"
        assert result.row_labels == ["Food", "Fun"]
        assert result.series_labels == ["2025-01", "2025-02"]
        assert result.cells == [
            [pytest.approx(100.0), pytest.approx(50.0)],
            [pytest.approx(0.0), pytest.approx(30.0)],
        ]

    async def test_both_axes_carry_their_totals(
        self, report_svc: SavedReportService, session: AsyncSession
    ):
        await _seed_two_months(session)
        result = await report_svc.execute(_pivot_config())
        assert isinstance(result, PivotResult)
        assert result.row_totals == [pytest.approx(150.0), pytest.approx(30.0)]
        assert result.series_totals == [pytest.approx(100.0), pytest.approx(80.0)]

    async def test_a_report_without_a_series_is_still_a_list(
        self, report_svc: SavedReportService, session: AsyncSession
    ):
        await _seed_two_months(session)
        result = await report_svc.execute(_pivot_config(series=None))
        assert isinstance(result, ReportResult)
        assert result.labels == ["Food", "Fun"]

    async def test_a_dimension_cannot_be_its_own_series(self, report_svc: SavedReportService):
        with pytest.raises(ValidationError):
            await report_svc.execute(_pivot_config(series="category"))

    async def test_the_series_axis_runs_in_time_order_not_by_size(
        self, report_svc: SavedReportService, session: AsyncSession
    ):
        # February is the bigger month; a series axis ranked by size would put
        # it first and draw a line that runs backwards.
        await _seed_two_months(session)
        result = await report_svc.execute(_pivot_config())
        assert isinstance(result, PivotResult)
        assert result.series_labels == ["2025-01", "2025-02"]

    async def test_a_weekday_axis_runs_in_weekday_order(
        self, report_svc: SavedReportService, session: AsyncSession
    ):
        # 2025-01-10 is a Friday, 2025-02-10 a Monday, 2025-02-15 a Saturday.
        await _seed_two_months(session)
        result = await report_svc.execute(_pivot_config(series="weekday"))
        assert isinstance(result, PivotResult)
        assert result.series_labels == ["Monday", "Friday", "Saturday"]

    async def test_top_n_cuts_rows_and_folds_the_rest_into_one(
        self, report_svc: SavedReportService, session: AsyncSession
    ):
        await _seed_two_months(session)
        result = await report_svc.execute(_pivot_config(top_n=1))
        assert isinstance(result, PivotResult)
        assert result.row_labels == ["Food", "Other"]
        # The ledger still adds up: what the cut left out is in the Other row,
        # so the column totals match the uncut report's.
        assert result.series_totals == [pytest.approx(100.0), pytest.approx(80.0)]

    async def test_top_n_never_cuts_the_series_axis(
        self, report_svc: SavedReportService, session: AsyncSession
    ):
        await _seed_two_months(session)
        result = await report_svc.execute(_pivot_config(top_n=1))
        assert isinstance(result, PivotResult)
        assert result.series_labels == ["2025-01", "2025-02"]

    async def test_the_rows_kept_are_the_biggest_ones(
        self, report_svc: SavedReportService, session: AsyncSession
    ):
        # Not the first ones on the axis: with months on the rows, a cut that
        # kept the earliest would answer a question nobody asked. February is
        # made the bigger month here so the two rules disagree.
        account, fun = await _seed_two_months(session)
        await TransactionService(session).create(
            TransactionCreate(
                account_id=account,
                category_id=fun,
                amount=Decimal("100.00"),
                type=TransactionType.EXPENSE,
                date=datetime.date(2025, 2, 20),
                description="february pushes ahead",
            )
        )
        result = await report_svc.execute(
            _pivot_config(dimension="month", series="category", top_n=1)
        )
        assert isinstance(result, PivotResult)
        assert result.row_labels == ["2025-02", "Other"]

    async def test_split_lines_land_in_their_own_category_and_month(
        self, report_svc: SavedReportService, session: AsyncSession
    ):
        """Covers the flows path: a split row is two cells, not one."""
        await _seed_split_lidl(session)
        result = await report_svc.execute(
            _pivot_config(date_from="2025-06-01", date_to="2025-06-30")
        )
        assert isinstance(result, PivotResult)
        assert result.series_labels == ["2025-06"]
        by_row = dict(zip(result.row_labels, result.cells, strict=True))
        assert by_row["Groceries"] == [pytest.approx(180.0)]
        assert by_row["Alcohol"] == [pytest.approx(34.5)]

    async def test_two_axes_that_need_the_same_table_join_it_once(
        self, report_svc: SavedReportService, session: AsyncSession
    ):
        # Account and Institution both hang off `accounts`; joining it twice
        # is a SQL error rather than a wider answer.
        await _seed_two_months(session)
        result = await report_svc.execute(_pivot_config(dimension="account", series="institution"))
        assert isinstance(result, PivotResult)
        assert result.row_labels == ["Checking"]
        assert result.series_labels == ["No Institution"]
        assert result.cells == [[pytest.approx(180.0)]]
