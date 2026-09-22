# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for problem reports: creation, triage, retention and delivery."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import NotFoundError, ValidationError
from kaleta.models.bug_report import BugReport, BugReportStatus
from kaleta.services import bug_report_delivery
from kaleta.services.bug_report_service import (
    RATE_LIMIT_PER_SESSION,
    BugReportService,
    decode_log_excerpt,
    webhook_payload,
)

LOG_LINES = [{"ts": "2026-09-22T10:00:00+00:00", "level": "INFO", "msg": "opened /budgets"}]


async def _create(service: BugReportService, **overrides: Any) -> BugReport:
    payload: dict[str, Any] = {
        "summary": "Budget page will not load",
        "description": "I clicked Budgets and got an error toast.",
        "event_ids": ["EV123456"],
        "route": "/budgets",
        "session_id": "sess-1",
    }
    payload.update(overrides)
    return await service.create(**payload)


class TestCreate:
    @pytest.mark.asyncio
    async def test_a_report_keeps_the_words_and_the_context(self, session: AsyncSession) -> None:
        report = await _create(BugReportService(session))
        assert report.report_id
        assert report.summary == "Budget page will not load"
        assert report.description == "I clicked Budgets and got an error toast."
        assert report.event_ids == ["EV123456"]
        assert report.route == "/budgets"
        assert report.status == BugReportStatus.NEW
        assert report.app_version

    @pytest.mark.asyncio
    async def test_no_log_excerpt_unless_the_box_was_ticked(self, session: AsyncSession) -> None:
        report = await _create(BugReportService(session))
        assert report.log_excerpt is None

    @pytest.mark.asyncio
    async def test_ticking_the_box_attaches_the_ring_buffer(self, session: AsyncSession) -> None:
        report = await _create(BugReportService(session), log_records=LOG_LINES)
        assert report.log_excerpt is not None
        assert json.loads(report.log_excerpt) == LOG_LINES

    @pytest.mark.asyncio
    async def test_an_empty_summary_is_refused(self, session: AsyncSession) -> None:
        with pytest.raises(ValidationError):
            await _create(BugReportService(session), summary="   ")

    @pytest.mark.asyncio
    async def test_an_empty_description_is_refused(self, session: AsyncSession) -> None:
        with pytest.raises(ValidationError):
            await _create(BugReportService(session), description="")

    @pytest.mark.asyncio
    async def test_a_session_may_file_five_reports_an_hour(self, session: AsyncSession) -> None:
        service = BugReportService(session)
        for _ in range(RATE_LIMIT_PER_SESSION):
            await _create(service)
        with pytest.raises(ValidationError):
            await _create(service)

    @pytest.mark.asyncio
    async def test_the_limit_is_per_session(self, session: AsyncSession) -> None:
        service = BugReportService(session)
        for _ in range(RATE_LIMIT_PER_SESSION):
            await _create(service)
        other = await _create(service, session_id="sess-2")
        assert other.report_id


class TestListAndTriage:
    @pytest.mark.asyncio
    async def test_list_filters_by_status(self, session: AsyncSession) -> None:
        service = BugReportService(session)
        first = await _create(service)
        await _create(service, summary="Second one")
        await service.mark(first.report_id, BugReportStatus.SEEN)

        assert [r.report_id for r in await service.list(BugReportStatus.SEEN)] == [first.report_id]
        assert len(await service.list(BugReportStatus.NEW)) == 1

    @pytest.mark.asyncio
    async def test_list_filters_by_user(self, session: AsyncSession) -> None:
        service = BugReportService(session)
        await _create(service)
        assert await service.list(user_id=42) == []

    @pytest.mark.asyncio
    async def test_mark_moves_a_report_through_triage(self, session: AsyncSession) -> None:
        service = BugReportService(session)
        report = await _create(service)
        closed = await service.mark(report.report_id, BugReportStatus.CLOSED)
        assert closed.status == BugReportStatus.CLOSED

    @pytest.mark.asyncio
    async def test_an_external_ref_records_the_issue_it_became(self, session: AsyncSession) -> None:
        service = BugReportService(session)
        report = await _create(service)
        url = "https://github.com/DawidAdamski/kaleta/issues/42"
        assert (await service.attach_external_ref(report.report_id, url)).external_ref == url

    @pytest.mark.asyncio
    async def test_an_unknown_report_is_not_found(self, session: AsyncSession) -> None:
        with pytest.raises(NotFoundError):
            await BugReportService(session).get("NOPE1234")

    @pytest.mark.asyncio
    async def test_a_user_can_withdraw_their_own_report(self, session: AsyncSession) -> None:
        service = BugReportService(session)
        report = await _create(service, user_id=7)
        await service.delete(report.report_id, user_id=7)
        with pytest.raises(NotFoundError):
            await service.get(report.report_id)

    @pytest.mark.asyncio
    async def test_a_user_cannot_withdraw_someone_elses_report(self, session: AsyncSession) -> None:
        service = BugReportService(session)
        report = await _create(service, user_id=7)
        with pytest.raises(NotFoundError):
            await service.delete(report.report_id, user_id=8)


class TestRetention:
    @pytest.mark.asyncio
    async def test_the_reaper_deletes_reports_past_the_window(self, session: AsyncSession) -> None:
        service = BugReportService(session)
        fresh = await _create(service)
        session.add(
            BugReport(
                report_id="OLDREP01",
                created_at=datetime.now(UTC) - timedelta(days=120),
                summary="ancient",
                description="ancient",
                event_ids=[],
                app_version="test",
                status=BugReportStatus.NEW,
            )
        )
        await session.commit()

        deleted = await service.purge_older_than(90)
        assert deleted == 1
        assert (await service.get(fresh.report_id)).report_id == fresh.report_id
        with pytest.raises(NotFoundError):
            await service.get("OLDREP01")

    @pytest.mark.asyncio
    async def test_a_window_below_one_day_purges_nothing(self, session: AsyncSession) -> None:
        service = BugReportService(session)
        await _create(service)
        assert await service.purge_older_than(0) == 0


class TestWebhookPayload:
    @pytest.mark.asyncio
    async def test_the_log_excerpt_is_left_out_by_default(self, session: AsyncSession) -> None:
        report = await _create(BugReportService(session), log_records=LOG_LINES)
        payload = webhook_payload(report)
        assert "log_excerpt" not in payload
        assert payload["report_id"] == report.report_id
        assert payload["event_ids"] == ["EV123456"]

    @pytest.mark.asyncio
    async def test_the_log_excerpt_is_included_only_when_asked(self, session: AsyncSession) -> None:
        report = await _create(BugReportService(session), log_records=LOG_LINES)
        assert webhook_payload(report, include_logs=True)["log_excerpt"] == LOG_LINES

    def test_a_corrupt_excerpt_reads_back_as_nothing(self) -> None:
        assert decode_log_excerpt("not json") == []
        assert decode_log_excerpt(None) == []


class TestDelivery:
    @pytest.mark.asyncio
    async def test_a_failing_webhook_never_reaches_the_caller(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(bug_report_delivery, "webhook_url", lambda: "https://example.invalid")
        monkeypatch.setattr(bug_report_delivery, "email_recipient", lambda: None)

        async def _boom(_url: str, _payload: dict[str, Any]) -> bool:
            raise RuntimeError("webhook is down")

        monkeypatch.setattr(bug_report_delivery, "_post_webhook", _boom)
        assert await bug_report_delivery.deliver({"report_id": "AB123456"}) is False

    @pytest.mark.asyncio
    async def test_a_working_webhook_reports_delivery(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sent: list[dict[str, Any]] = []
        monkeypatch.setattr(bug_report_delivery, "webhook_url", lambda: "https://example.test")
        monkeypatch.setattr(bug_report_delivery, "email_recipient", lambda: None)

        async def _ok(_url: str, payload: dict[str, Any]) -> bool:
            sent.append(payload)
            return True

        monkeypatch.setattr(bug_report_delivery, "_post_webhook", _ok)
        assert await bug_report_delivery.deliver({"report_id": "AB123456"}) is True
        assert sent == [{"report_id": "AB123456"}]

    @pytest.mark.asyncio
    async def test_with_nothing_configured_delivery_is_a_no_op(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(bug_report_delivery, "webhook_url", lambda: None)
        monkeypatch.setattr(bug_report_delivery, "email_recipient", lambda: None)
        assert await bug_report_delivery.deliver({"report_id": "AB123456"}) is False
