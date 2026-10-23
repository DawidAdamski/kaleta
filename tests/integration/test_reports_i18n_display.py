# SPDX-License-Identifier: AGPL-3.0-or-later
"""A Polish session reads report headers and row labels in Polish.

``SavedReportService`` stays presentation-free: it emits dimension/metric
i18n keys, weekday ordinals and stable sentinels for the buckets no language
spells the same. Only the report views call ``t()``. This test runs the real
service against the database, asserts it emits identifiers (never words), then
localizes through the view helper under a Polish session and checks the words.
"""

from __future__ import annotations

import dataclasses
import datetime
from decimal import Decimal
from types import SimpleNamespace

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
    NO_INSTITUTION_LABEL,
    OTHER_ROW_LABEL,
    TYPE_LABEL_PREFIX,
    UNCATEGORISED_LABEL,
    WEEKDAY_LABEL_PREFIX,
    PivotResult,
    ReportConfig,
    ReportResult,
    weekday_label,
)
from kaleta.views.reports.chart_zone import _localize, _resolve_label


def _speak_polish(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make ``t()`` resolve against the Polish locale, as a signed-in pl user."""

    class _UserStorage(dict):
        def get(self, key: str, default: object = None) -> object:
            return dict.get(self, key, default)

    class _FakeApp:
        storage = SimpleNamespace(user=_UserStorage(language="pl"))

    monkeypatch.setattr("nicegui.app", _FakeApp(), raising=False)


async def _seed(session: AsyncSession) -> int:
    """Two categorised expenses, one income, and an uncategorised split line.

    2025-02-10 is a Monday, so the weekday and type reports each have something
    to group. A plain expense or income must carry a category, so the
    uncategorised bucket (the one that exercises the fallback) is a split
    expense whose single line has no category.
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
    income_cat = (
        await CategoryService(session).create(
            CategoryCreate(name="Salary", type=CategoryType.INCOME)
        )
    ).id
    for category_id, amount, tx_type in (
        (food, "100.00", TransactionType.EXPENSE),
        (fun, "40.00", TransactionType.EXPENSE),
        (income_cat, "500.00", TransactionType.INCOME),
    ):
        await TransactionService(session).create(
            TransactionCreate(
                account_id=account,
                category_id=category_id,
                amount=Decimal(amount),
                type=tx_type,
                date=datetime.date(2025, 2, 10),
                description="pl report fixture",
            )
        )
    # A split expense whose only line carries no category — the flows path
    # attributes it to the uncategorised bucket.
    await TransactionService(session).create(
        TransactionCreate(
            account_id=account,
            amount=Decimal("10.00"),
            type=TransactionType.EXPENSE,
            date=datetime.date(2025, 2, 10),
            description="uncategorised split",
            is_split=True,
            splits=[TransactionSplitCreate(category_id=None, amount=Decimal("10.00"))],
        )
    )
    return account


class TestPolishReportDisplay:
    async def test_the_service_emits_identifiers_not_words(self, session: AsyncSession) -> None:
        """Covers: KAL-RPT-012"""
        await _seed(session)
        svc = SavedReportService(session)
        config = ReportConfig(
            dimension="weekday",
            metric="sum",
            transaction_types=["expense"],
            date_preset="custom",
            date_from="2025-02-01",
            date_to="2025-02-28",
        )
        weekday = await svc.execute(config)
        assert isinstance(weekday, ReportResult)
        # Keys and ordinals, never English words: this is the invariant.
        assert weekday.metric_header == "metric_sum"
        assert weekday.column_header == "dim_weekday"
        assert weekday.labels == [weekday_label(1)]  # Monday, Postgres dow 1

    async def test_a_polish_session_reads_headers_and_labels_in_polish(
        self, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Covers: KAL-RPT-012"""
        await _seed(session)
        svc = SavedReportService(session)

        def _config(**overrides: object) -> ReportConfig:
            base = ReportConfig(
                metric="sum",
                date_preset="custom",
                date_from="2025-02-01",
                date_to="2025-02-28",
            )
            return dataclasses.replace(base, **overrides)

        weekday = await svc.execute(_config(dimension="weekday", transaction_types=["expense"]))
        by_type = await svc.execute(
            _config(dimension="type", transaction_types=["expense", "income"])
        )
        # The uncategorised bucket is the split line with no category of its own.
        uncategorised = await svc.execute(
            _config(dimension="category", transaction_types=["expense"])
        )

        # The service hands back sentinels; the view has not spoken yet.
        assert isinstance(by_type, ReportResult)
        assert any(label.startswith(TYPE_LABEL_PREFIX) for label in by_type.labels)
        assert isinstance(uncategorised, ReportResult)
        assert UNCATEGORISED_LABEL in uncategorised.labels

        # Now speak Polish and localize through the view, as the page does.
        _speak_polish(monkeypatch)

        localized_weekday = _localize(weekday)
        assert isinstance(localized_weekday, ReportResult)
        assert localized_weekday.metric_header == "Suma kwot"
        assert localized_weekday.labels == ["Poniedziałek"]

        localized_type = _localize(by_type)
        assert isinstance(localized_type, ReportResult)
        assert "Wydatek" in localized_type.labels
        assert "Przychód" in localized_type.labels

        localized_uncat = _localize(uncategorised)
        assert isinstance(localized_uncat, ReportResult)
        assert "Bez kategorii" in localized_uncat.labels

        # The folded top-N row and the institution fallback resolve too.
        assert _resolve_label(OTHER_ROW_LABEL) == "Pozostałe"
        assert _resolve_label(NO_INSTITUTION_LABEL) == "Brak instytucji"

    async def test_a_pivot_folds_into_a_polish_other_row(
        self, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Covers: KAL-RPT-012"""
        await _seed(session)
        svc = SavedReportService(session)
        pivot = await svc.execute(
            ReportConfig(
                dimension="category",
                series="month",
                metric="sum",
                transaction_types=["expense"],
                date_preset="custom",
                date_from="2025-02-01",
                date_to="2025-02-28",
                top_n=1,
            )
        )
        assert isinstance(pivot, PivotResult)
        # The service folds the cut rows under the sentinel, not the word.
        assert OTHER_ROW_LABEL in pivot.row_labels
        assert pivot.row_header == "dim_category"

        _speak_polish(monkeypatch)
        localized = _localize(pivot)
        assert isinstance(localized, PivotResult)
        assert localized.row_header == "Kategoria"
        assert "Pozostałe" in localized.row_labels
        assert not any(label.startswith(WEEKDAY_LABEL_PREFIX) for label in localized.row_labels)
