# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for SavedReportService view helpers and query execution."""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.account import AccountType
from kaleta.models.category import CategoryType
from kaleta.models.transaction import TransactionType
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.category import CategoryCreate
from kaleta.schemas.transaction import TransactionCreate, TransactionSplitCreate
from kaleta.services import AccountService, CategoryService, SavedReportService, TransactionService
from kaleta.services.saved_report_service import (
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
