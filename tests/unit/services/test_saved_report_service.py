"""Unit tests for SavedReportService view helpers."""

from __future__ import annotations

from kaleta.services.saved_report_service import (
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
