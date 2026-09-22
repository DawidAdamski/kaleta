#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read and triage the bug reports users filed from the app.

    scripts/bug_reports.py list [--status new|seen|closed]
    scripts/bug_reports.py show <report_id>
    scripts/bug_reports.py close <report_id> [--ref <issue url>]

Reads the database the app is configured to use (``~/.kaleta/config.json``,
or ``KALETA_DB_URL``).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kaleta.config import settings
from kaleta.config.setup_config import get_db_url
from kaleta.db import configure_database
from kaleta.exceptions import KaletaError
from kaleta.models.bug_report import BugReportStatus
from kaleta.services import with_session
from kaleta.services.bug_report_service import BugReportService, decode_log_excerpt


def _connect() -> None:
    db_url = get_db_url() or settings.db_url
    configure_database(db_url, debug=settings.debug)


async def _list(status: str | None) -> int:
    wanted = BugReportStatus(status) if status else None

    async def _query(session: Any) -> list[Any]:
        return await BugReportService(session).list(wanted)

    reports = await with_session(_query)
    if not reports:
        print("No bug reports.")
        return 0
    print(f"{'REPORT':<10} {'WHEN':<17} {'STATUS':<7} {'EVENTS':<20} SUMMARY")
    for report in reports:
        events = ",".join(report.event_ids or [])[:20]
        when = report.created_at.strftime("%Y-%m-%d %H:%M")
        print(
            f"{report.report_id:<10} {when:<17} {str(report.status):<7} "
            f"{events:<20} {report.summary}"
        )
    return 0


async def _show(report_id: str) -> int:
    async def _query(session: Any) -> tuple[Any, list[Any]]:
        service = BugReportService(session)
        report = await service.get(report_id)
        from kaleta.services.event_service import EventService

        events = []
        for event_id in report.event_ids or []:
            event = await EventService(session).get_by_event_id(str(event_id))
            if event is not None:
                events.append(event)
        return report, events

    report, events = await with_session(_query)

    print(f"Report:   {report.report_id}")
    print(f"When:     {report.created_at.isoformat()}")
    print(f"Status:   {report.status}")
    print(f"Version:  {report.app_version}")
    print(f"Route:    {report.route or '—'}")
    print(f"Browser:  {report.user_agent or '—'}")
    print(f"Window:   {report.viewport or '—'}  Locale: {report.locale or '—'}")
    print(f"Contact:  {report.contact_email or '—'}")
    print(f"External: {report.external_ref or '—'}")
    print()
    print(f"Summary:  {report.summary}")
    print()
    print(report.description)

    for event in events:
        print()
        print(f"--- event {event.event_id} ({event.exception_class}) ---")
        print(event.stack_trace)

    lines = decode_log_excerpt(report.log_excerpt)
    if lines:
        print()
        print(f"--- log excerpt ({len(lines)} lines) ---")
        for line in lines:
            print(f"{line.get('ts', ''):<32} {line.get('level', ''):<8} {line.get('msg', '')}")
    return 0


async def _close(report_id: str, external_ref: str | None) -> int:
    async def _run(session: Any) -> Any:
        service = BugReportService(session)
        if external_ref:
            await service.attach_external_ref(report_id, external_ref)
        return await service.mark(report_id, BugReportStatus.CLOSED)

    report = await with_session(_run)
    print(f"{report.report_id} closed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    list_cmd = sub.add_parser("list", help="list reports, newest first")
    list_cmd.add_argument("--status", choices=[s.value for s in BugReportStatus])

    show_cmd = sub.add_parser("show", help="print one report with its traces and logs")
    show_cmd.add_argument("report_id")

    close_cmd = sub.add_parser("close", help="mark a report closed")
    close_cmd.add_argument("report_id")
    close_cmd.add_argument("--ref", help="GitHub issue URL to record on the report")

    args = parser.parse_args()
    _connect()

    try:
        if args.command == "list":
            return asyncio.run(_list(args.status))
        if args.command == "show":
            return asyncio.run(_show(args.report_id))
        return asyncio.run(_close(args.report_id, args.ref))
    except KaletaError as exc:
        print(f"error: {exc.message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
