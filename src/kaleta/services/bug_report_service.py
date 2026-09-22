# SPDX-License-Identifier: AGPL-3.0-or-later
"""Problem reports written by users, and the diagnostics they agreed to attach."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.config import settings
from kaleta.exceptions import NotFoundError, ValidationError
from kaleta.models.bug_report import BugReport, BugReportStatus
from kaleta.observability import MAX_RECORDS, app_version
from kaleta.services.event_service import generate_short_id

logger = logging.getLogger(__name__)

MAX_SUMMARY_CHARS = 120
MAX_DESCRIPTION_CHARS = 5000
#: Reports one session may file within :data:`RATE_LIMIT_WINDOW_HOURS`.
RATE_LIMIT_PER_SESSION = 5
RATE_LIMIT_WINDOW_HOURS = 1
_MAX_REPORT_ID_ATTEMPTS = 5


def _required(value: str | None, *, field: str) -> str:
    text = (value or "").strip()
    if not text:
        raise ValidationError(f"{field} is required")
    return text


def encode_log_excerpt(records: list[dict[str, Any]] | None) -> str | None:
    """Serialise the ring buffer for storage, capped at the buffer size."""
    if not records:
        return None
    return json.dumps(records[-MAX_RECORDS:], ensure_ascii=False)


def decode_log_excerpt(raw: str | None) -> list[dict[str, Any]]:
    """Read back what :func:`encode_log_excerpt` wrote; never raise on junk."""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def webhook_payload(report: BugReport, *, include_logs: bool = False) -> dict[str, Any]:
    """The JSON a delivery route receives — the log excerpt only when asked."""
    payload: dict[str, Any] = {
        "report_id": report.report_id,
        "created_at": report.created_at.isoformat() if report.created_at else None,
        "summary": report.summary,
        "description": report.description,
        "contact_email": report.contact_email,
        "event_ids": list(report.event_ids or []),
        "route": report.route,
        "app_version": report.app_version,
        "user_agent": report.user_agent,
        "viewport": report.viewport,
        "locale": report.locale,
        "status": str(report.status),
    }
    if include_logs:
        payload["log_excerpt"] = decode_log_excerpt(report.log_excerpt)
    return payload


class BugReportService:
    """Create, triage and expire the reports users send from the app."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        summary: str,
        description: str,
        event_ids: list[str] | None = None,
        route: str | None = None,
        user_agent: str | None = None,
        viewport: str | None = None,
        locale: str | None = None,
        contact_email: str | None = None,
        session_id: str | None = None,
        user_id: int | None = None,
        log_records: list[dict[str, Any]] | None = None,
    ) -> BugReport:
        """Persist one report; ``log_records`` is attached only when passed."""
        clean_summary = _required(summary, field="Summary")[:MAX_SUMMARY_CHARS]
        clean_description = _required(description, field="Description")[:MAX_DESCRIPTION_CHARS]
        await self._enforce_rate_limit(session_id)

        report = BugReport(
            report_id=await self._allocate_report_id(),
            created_at=datetime.now(UTC),
            user_id=user_id,
            session_id=session_id,
            contact_email=(contact_email or "").strip() or None,
            summary=clean_summary,
            description=clean_description,
            event_ids=list(event_ids or []),
            route=route,
            app_version=app_version(),
            user_agent=user_agent,
            viewport=viewport,
            locale=locale,
            log_excerpt=encode_log_excerpt(log_records),
            status=BugReportStatus.NEW,
        )
        self.session.add(report)
        await self.session.commit()
        await self.session.refresh(report)
        logger.info(
            "Bug report %s filed (events=%s, logs=%s)",
            report.report_id,
            len(report.event_ids or []),
            report.log_excerpt is not None,
        )
        return report

    async def list(
        self,
        status: BugReportStatus | None = None,
        *,
        user_id: int | None = None,
        limit: int = 100,
    ) -> list[BugReport]:
        stmt = select(BugReport).order_by(BugReport.created_at.desc()).limit(limit)
        if status is not None:
            stmt = stmt.where(BugReport.status == status)
        if user_id is not None:
            stmt = stmt.where(BugReport.user_id == user_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get(self, report_id: str) -> BugReport:
        result = await self.session.execute(
            select(BugReport).where(BugReport.report_id == report_id.upper()).limit(1)
        )
        report = result.scalar_one_or_none()
        if report is None:
            raise NotFoundError(f"Bug report {report_id} not found")
        return report

    async def mark(self, report_id: str, status: BugReportStatus) -> BugReport:
        report = await self.get(report_id)
        report.status = status
        await self.session.commit()
        await self.session.refresh(report)
        return report

    async def attach_external_ref(self, report_id: str, external_ref: str) -> BugReport:
        report = await self.get(report_id)
        report.external_ref = external_ref
        await self.session.commit()
        await self.session.refresh(report)
        return report

    async def delete(self, report_id: str, *, user_id: int | None = None) -> None:
        """Withdraw a report — the user may always take their words back."""
        report = await self.get(report_id)
        if user_id is not None and report.user_id != user_id:
            raise NotFoundError(f"Bug report {report_id} not found")
        await self.session.delete(report)
        await self.session.commit()

    async def purge_older_than(self, days: int) -> int:
        if days < 1:
            return 0
        cutoff = datetime.now(UTC) - timedelta(days=days)
        stmt = delete(BugReport).where(BugReport.created_at < cutoff)
        result = await self.session.execute(stmt.execution_options(synchronize_session=False))
        await self.session.commit()
        return int(getattr(result, "rowcount", 0) or 0)

    async def _allocate_report_id(self) -> str:
        for _ in range(_MAX_REPORT_ID_ATTEMPTS):
            candidate = generate_short_id()
            existing = await self.session.scalar(
                select(BugReport.id).where(BugReport.report_id == candidate).limit(1)
            )
            if existing is None:
                return candidate
        raise ValidationError("Could not allocate a unique report id")

    async def _enforce_rate_limit(self, session_id: str | None) -> None:
        if session_id is None:
            return
        since = datetime.now(UTC) - timedelta(hours=RATE_LIMIT_WINDOW_HOURS)
        recent = await self.session.scalar(
            select(func.count(BugReport.id)).where(
                BugReport.session_id == session_id,
                BugReport.created_at >= since,
            )
        )
        if int(recent or 0) >= RATE_LIMIT_PER_SESSION:
            raise ValidationError(
                f"Too many reports from this session — try again in an hour "
                f"(limit {RATE_LIMIT_PER_SESSION} per hour)"
            )


def bug_reports_enabled() -> bool:
    return bool(settings.bug_reports_enabled)


def bug_report_retention_days() -> int:
    return int(settings.bug_report_retention_days)
